import io
import hashlib
import json
import re

from collections import defaultdict
from decimal import Decimal, InvalidOperation
from datetime import date, datetime
from functools import wraps
from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException
from zipfile import BadZipFile
from sqlalchemy.exc import IntegrityError
from app import db
from flask import (
    Blueprint,
    current_app,
    render_template,
    redirect,
    url_for,
    request,
    flash,
    abort,
    jsonify
)
from flask_login import (
    current_user,
    login_user,
    logout_user,
    login_required
)
from app.models import (
    WorkItem,
    PartsOrder,
    PartLine,
    Technician,
    Supplier,
    User,
    Notification,
    ReceiptImport
)

main = Blueprint("main", __name__)

def admin_required(view_function):
    @wraps(view_function)
    def wrapped_view(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("main.login"))

        if not current_user.is_admin:
            abort(403)

        return view_function(*args, **kwargs)

    return wrapped_view


@main.before_request
def require_login():
    if request.endpoint == "main.login":
        return None

    if not current_user.is_authenticated:
        return redirect(url_for("main.login"))

    if not current_user.is_active:
        logout_user()
        flash(
            "Your account has been deactivated. "
            "Please contact an administrator.",
            "danger"
        )
        return redirect(url_for("main.login"))


@main.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = User.query.filter_by(username=username).first()

        if user and user.is_active and user.check_password(password):
            login_user(user)
            flash("You have successfully logged in.", "success")
            return redirect(url_for("main.dashboard"))

        flash("Invalid username or password.", "danger")

    return render_template("login.html")


@main.route("/logout", methods=["POST"])
def logout():
    logout_user()
    flash("You have been logged out.", "success")
    return redirect(url_for("main.login"))


@main.route("/")
def dashboard():
    work_items = WorkItem.query.filter_by(
        is_archived=False
    ).order_by(WorkItem.created_at.desc()).all()

    total_items = len(work_items)

    green_count = 0
    yellow_count = 0
    red_count = 0
    booked_count = 0

    # Calculate status and counts for all active Work Items
    for item in work_items:

        total_ordered = sum(
            part.quantity_ordered
            for order in item.parts_orders
            for part in order.parts
        )

        total_received = sum(
            part.quantity_received
            for order in item.parts_orders
            for part in order.parts
        )

        # Calculate the actual parts receiving status
        if total_ordered == 0 or total_received == 0:
            item.parts_status = "Red"

        elif total_received >= total_ordered:
            item.parts_status = "Green"

        else:
            item.parts_status = "Yellow"
        
        # Appointment date takes priority for dashboard display
        if item.appointment_date is not None:
            item.receiving_status = "Blue"
        else:
            item.receiving_status = item.parts_status

        # Count Work Items by status
        if item.receiving_status == "Blue":
            booked_count += 1

        elif item.receiving_status == "Green":
            green_count += 1

        elif item.receiving_status == "Yellow":
            yellow_count += 1

        else:
            red_count += 1

    # Get search value
    search_query = request.args.get("search", "").strip().lower()

    # Filter Work Items by search text
    filtered_items = work_items

    if search_query:
        filtered_items = [
            item for item in filtered_items
            if search_query in str(item.number).lower()
            or search_query in (item.customer or "").lower()
            or search_query in (item.technician or "").lower()
            or search_query in (item.type or "").lower()
        ]

    technicians = Technician.query.order_by(
        Technician.name.asc()
    ).all()

    return render_template(
        "dashboard.html",
        work_items=filtered_items,
        total_items=total_items,
        green_count=green_count,
        yellow_count=yellow_count,
        red_count=red_count,
        booked_count=booked_count,
        search_query=search_query,
        technicians=technicians
    )


@main.route("/work-item/<int:item_id>")
def work_item_details(item_id):
    work_item = db.get_or_404(WorkItem, item_id)

    suppliers = Supplier.query.order_by(Supplier.name.asc()).all()

    total_ordered = sum(
        part.quantity_ordered
        for order in work_item.parts_orders
        for part in order.parts
    )

    total_received = sum(
        part.quantity_received
        for order in work_item.parts_orders
        for part in order.parts
    )

    if total_ordered == 0 or total_received == 0:
        status = "Red"

    elif total_received >= total_ordered:
        status = "Green"

    else:
        status = "Yellow"

    return render_template(
        "work_item_details.html",
        work_item=work_item,
        total_ordered=total_ordered,
        total_received=total_received,
        status=status,
        suppliers=suppliers
    )


@main.route("/check-work-item", methods=["POST"])
def check_work_item():

    number = request.form.get("number", "").strip()
    item_type = request.form.get("type", "").strip()

    # Validate required fields
    if not number or not item_type:
        return jsonify({
            "success": False,
            "message": "Work Item Number and Type are required."
        }), 400

    # Check both active and archived Work Items
    existing_work_item = WorkItem.query.filter_by(
        number=number,
        type=item_type
    ).first()

    if existing_work_item:
        return jsonify({
            "success": True,
            "exists": True,
            "work_item": {
                "id": existing_work_item.id,
                "number": existing_work_item.number,
                "type": existing_work_item.type,
                "customer": existing_work_item.customer,
                "is_archived": existing_work_item.is_archived,
                "url": url_for(
                    "main.work_item_details",
                    item_id=existing_work_item.id
                )
            }
        })

    return jsonify({
        "success": True,
        "exists": False,
        "new_work_item_url": url_for(
            "main.new_work_item",
            number=number,
            type=item_type
        )
    })


@main.route("/new-work-item", methods=["GET", "POST"])
def new_work_item():
    suppliers = Supplier.query.order_by(Supplier.name.asc()).all()

    if request.method == "POST":
        number = request.form.get("number", "").strip()
        item_type = request.form.get("type", "").strip()
        customer = request.form.get("customer", "").strip().upper()
        technician = request.form.get("technician", "").strip()
        notes = request.form.get("notes", "").strip()

        if not number or not item_type or not customer:
            flash(
                "Work Item Number, Type, and Customer are required.",
                "danger"
            )
            return redirect(url_for("main.new_work_item"))


        # Check whether this Work Item Number and Type already exist
        existing_work_item = WorkItem.query.filter_by(
            number=number,
            type=item_type
        ).first()

        if existing_work_item:
            flash(
                f"Work Item {number} ({item_type}) already exists. "
                "Please use a different Work Item Number or Type.",
                "danger"
            )
            return redirect(url_for("main.new_work_item"))


        try:
            order_count = int(request.form.get("order_count", "0"))
        except ValueError:
            flash("Invalid Supplier Order count.", "danger")
            return redirect(url_for("main.new_work_item"))

        if order_count < 0:
            flash("Supplier Order count cannot be negative.", "danger")
            return redirect(url_for("main.new_work_item"))

        # Validate all Supplier Orders and Parts before saving
        orders_data = []

        for order_index in range(order_count):
            supplier = request.form.get(
                f"order_{order_index}_supplier", ""
            ).strip()

            order_number = request.form.get(
                f"order_{order_index}_order_number", ""
            ).strip()

            order_notes = request.form.get(
                f"order_{order_index}_notes", ""
            ).strip()

            if not supplier:
                flash(
                    f"Supplier is required for Supplier Order "
                    f"{order_index + 1}.",
                    "danger"
                )
                return redirect(url_for("main.new_work_item"))

            try:
                part_count = int(
                    request.form.get(
                        f"order_{order_index}_part_count", "0"
                    )
                )
            except ValueError:
                flash("Invalid Part count.", "danger")
                return redirect(url_for("main.new_work_item"))

            if part_count < 0:
                flash("Part count cannot be negative.", "danger")
                return redirect(url_for("main.new_work_item"))

            parts_data = []

            for part_index in range(part_count):
                prefix = (
                    f"order_{order_index}_part_{part_index}"
                )

                part_number = request.form.get(
                    f"{prefix}_part_number", ""
                ).strip()

                description = request.form.get(
                    f"{prefix}_description", ""
                ).strip()

                part_notes = request.form.get(
                    f"{prefix}_notes", ""
                ).strip()

                try:
                    quantity_ordered = int(
                        request.form.get(
                            f"{prefix}_quantity_ordered", "1"
                        )
                    )

                    quantity_received = int(
                        request.form.get(
                            f"{prefix}_quantity_received", "0"
                        )
                    )
                except ValueError:
                    flash(
                        "Part quantities must be whole numbers.",
                        "danger"
                    )
                    return redirect(url_for("main.new_work_item"))

                if not part_number or not description:
                    flash(
                        "Part Number and Description are required.",
                        "danger"
                    )
                    return redirect(url_for("main.new_work_item"))

                if quantity_ordered <= 0:
                    flash(
                        "Quantity Ordered must be greater than zero.",
                        "danger"
                    )
                    return redirect(url_for("main.new_work_item"))

                if (
                    quantity_received < 0
                    or quantity_received > quantity_ordered
                ):
                    flash(
                        "Quantity Received must be between zero "
                        "and Quantity Ordered.",
                        "danger"
                    )
                    return redirect(url_for("main.new_work_item"))

                parts_data.append({
                    "part_number": part_number,
                    "description": description,
                    "quantity_ordered": quantity_ordered,
                    "quantity_received": quantity_received,
                    "notes": part_notes
                })

            orders_data.append({
                "supplier": supplier,
                "order_number": order_number,
                "notes": order_notes,
                "parts": parts_data
            })

        # Create the Work Item
        work_item = WorkItem(
            number=number,
            type=item_type,
            customer=customer,
            technician=technician,
            notes=notes
        )

        db.session.add(work_item)

        # Create Supplier Orders and Parts
        for order_data in orders_data:
            parts_order = PartsOrder(
                work_item=work_item,
                supplier=order_data["supplier"],
                order_number=order_data["order_number"],
                notes=order_data["notes"]
            )

            db.session.add(parts_order)

            for part_data in order_data["parts"]:
                part = PartLine(
                    parts_order=parts_order,
                    part_number=part_data["part_number"],
                    description=part_data["description"],
                    quantity_ordered=part_data["quantity_ordered"],
                    quantity_received=part_data["quantity_received"],
                    notes=part_data["notes"]
                )

                db.session.add(part)

            try:
                db.session.commit()

            except IntegrityError:
                db.session.rollback()

                # Check whether the failure was caused by a duplicate
                existing_work_item = WorkItem.query.filter_by(
                    number=number,
                    type=item_type
                ).first()

                if existing_work_item:
                    flash(
                        f"Work Item {number} ({item_type}) already exists. "
                        "Duplicate Work Items are not allowed.",
                        "danger"
                    )
                else:
                    flash(
                        "A database constraint prevented the Work Item "
                        "from being saved.",
                        "danger"
                    )

                return redirect(url_for("main.new_work_item"))

            except Exception:
                db.session.rollback()

                flash(
                    "An error occurred while saving the Work Item "
                    "and its Supplier Orders.",
                    "danger"
                )

                return redirect(url_for("main.new_work_item"))


        flash(
            "Work Item and Supplier Orders created successfully!",
            "success"
        )

        return redirect(url_for("main.dashboard"))

    return render_template(
        "new_work_item.html",
        suppliers=suppliers
    )


@main.route("/work-item/<int:item_id>/update-details", methods=["POST"])
def update_work_item_details(item_id):

    work_item = db.get_or_404(WorkItem, item_id)

    # Get updated values from the Edit Work Item modal
    number = request.form.get("number", "").strip()
    item_type = request.form.get("type", "").strip()
    customer = request.form.get("customer", "").strip().upper()

    # Validate required fields
    if not number or not item_type or not customer:
        flash(
            "Work Item Number, Type, and Customer are required.",
            "danger"
        )
        return redirect(
            url_for("main.work_item_details", item_id=item_id)
        )

    # Check for another Work Item with the same Number and Type
    existing_work_item = WorkItem.query.filter(
        WorkItem.number == number,
        WorkItem.type == item_type,
        WorkItem.id != item_id
    ).first()

    if existing_work_item:
        flash(
            f"Work Item {number} ({item_type}) already exists. "
            "Please use a different Work Item Number or Type.",
            "danger"
        )
        return redirect(
            url_for("main.work_item_details", item_id=item_id)
        )

    # Update only the three editable fields
    work_item.number = number
    work_item.type = item_type
    work_item.customer = customer

    try:
        db.session.commit()

    except IntegrityError:
        db.session.rollback()

        flash(
            "Unable to save changes. Another Work Item "
            "already uses this Number and Type.",
            "danger"
        )

        return redirect(
            url_for("main.work_item_details", item_id=item_id)
        )

    flash(
        "Work Item details updated successfully!",
        "success"
    )

    return redirect(
        url_for("main.work_item_details", item_id=item_id)
    )


@main.route("/work-item/<int:item_id>/add-order", methods=["POST"])
@login_required
def add_parts_order(item_id):
    work_item = db.get_or_404(WorkItem, item_id)

    supplier = request.form.get("supplier", "").strip()
    order_number = request.form.get("order_number", "").strip()
    notes = request.form.get("notes", "").strip()

    if not supplier:
        flash("Supplier is required.", "danger")
        return redirect(
            url_for("main.work_item_details", item_id=item_id)
        )

    parts_order = PartsOrder(
        work_item_id=work_item.id,
        supplier=supplier,
        order_number=order_number,
        notes=notes
    )

    db.session.add(parts_order)
    db.session.commit()

    flash("Supplier order added successfully!", "success")

    return redirect(
        url_for("main.work_item_details", item_id=item_id)
    )


@main.route("/archive/<int:item_id>", methods=["POST"])
def archive_work_item(item_id):
    work_item = db.session.get(WorkItem, item_id)

    if work_item:
        work_item.is_archived = True
        db.session.commit()
        flash("Work Item archived successfully.", "success")

    return redirect(url_for("main.dashboard"))


@main.route("/archive-past-booked-items", methods=["POST"])
def archive_past_booked_items():

    from datetime import date, datetime

    cutoff_date_str = request.form.get(
        "archive_cutoff_date", ""
    ).strip()

    try:
        cutoff_date = datetime.strptime(
            cutoff_date_str, "%Y-%m-%d"
        ).date()

    except ValueError:
        flash("Please select a valid archive date.", "danger")
        return redirect(url_for("main.archived_work_items"))

    # Do not allow today or future dates
    if cutoff_date >= date.today():
        flash(
            "The archive cutoff date must be before today.",
            "danger"
        )
        return redirect(url_for("main.archived_work_items"))

    # Find active Work Items booked on or before cutoff
    work_items = WorkItem.query.filter(
        WorkItem.is_archived.is_(False),
        WorkItem.appointment_date.isnot(None),
        WorkItem.appointment_date <= cutoff_date
    ).all()

    archived_count = len(work_items)

    if archived_count == 0:
        flash(
            "No Work Items found with a Booked In Date "
            "on or before the selected date.",
            "info"
        )
    else:
        for item in work_items:
            item.is_archived = True

        db.session.commit()

        flash(
            f"{archived_count} Work Item(s) archived successfully!",
            "success"
        )

    return redirect(url_for("main.archived_work_items"))


@main.route("/archive")
def archived_work_items():
    from datetime import date, timedelta

    yesterday = date.today() - timedelta(days=1)    
    work_items = (
        WorkItem.query
        .filter_by(is_archived=True)
        .order_by(WorkItem.created_at.desc())
        .all()
    )

    return render_template(
        "archive.html",        
        work_items=work_items,
        yesterday=yesterday.isoformat()
    )


@main.route("/restore/<int:item_id>", methods=["POST"])
def restore_work_item(item_id):
    work_item = db.session.get(WorkItem, item_id)

    if work_item:
        work_item.is_archived = False
        db.session.commit()

        flash("Work Item restored successfully.", "success")

    return redirect(url_for("main.archived_work_items"))


@main.route("/archive/delete-old", methods=["POST"])
def delete_old_archived_items():
    cutoff_text = request.form.get("cutoff_date", "").strip()

    try:
        cutoff_date = date.fromisoformat(cutoff_text)
    except ValueError:
        flash("Please select a valid date.", "danger")
        return redirect(url_for("main.archived_work_items"))

    if request.form.get("confirm_delete") != "yes":
        flash("Deletion was not confirmed.", "warning")
        return redirect(url_for("main.archived_work_items"))

    archived_items = WorkItem.query.filter_by(
        is_archived=True
    ).all()

    items_to_delete = [
        item for item in archived_items
        if item.created_at.date() < cutoff_date
    ]

    if not items_to_delete:
        flash(
            "No archived Work Items were found before the selected date.",
            "info"
        )
        return redirect(url_for("main.archived_work_items"))

    deleted_count = len(items_to_delete)

    for item in items_to_delete:
        db.session.delete(item)

    db.session.commit()

    flash(
        f"{deleted_count} archived Work Item(s) permanently deleted.",
        "success"
    )

    return redirect(url_for("main.archived_work_items"))


@main.route("/parts-order/<int:order_id>/add-part", methods=["POST"])
def add_part(order_id):
    parts_order = db.get_or_404(PartsOrder, order_id)

    part_number = request.form.get("part_number", "").strip()
    description = request.form.get("description", "").strip()
    notes = request.form.get("notes", "").strip()

    try:
        quantity_ordered = int(
            request.form.get("quantity_ordered", "1")
        )
        quantity_received = int(
            request.form.get("quantity_received", "0")
        )
    except ValueError:
        flash("Quantities must be whole numbers.", "danger")
        return redirect(
            url_for(
                "main.work_item_details",
                item_id=parts_order.work_item_id
            )
        )

    if not part_number or not description:
        flash("Part Number and Description are required.", "danger")

    elif quantity_ordered <= 0:
        flash("Quantity Ordered must be greater than zero.", "danger")

    elif quantity_received < 0 or quantity_received > quantity_ordered:
        flash(
            "Quantity Received must be between zero and Quantity Ordered.",
            "danger"
        )

    else:
        part = PartLine(
            parts_order_id=parts_order.id,
            part_number=part_number,
            description=description,
            quantity_ordered=quantity_ordered,
            quantity_received=quantity_received,
            notes=notes
        )

        db.session.add(part)
        db.session.commit()

        flash("Part added successfully!", "success")

    return redirect(
        url_for(
            "main.work_item_details",
            item_id=parts_order.work_item_id
        )
    )


@main.route("/part/<int:part_id>/update-received", methods=["POST"])
def update_received(part_id):
    part = db.get_or_404(PartLine, part_id)

    work_item = part.parts_order.work_item

    # Record receiving status before updating the quantity.
    previous_status = get_receiving_status(work_item)

    try:
        quantity_received = int(
            request.form.get("quantity_received", "0")
        )
    except ValueError:
        flash("Received quantity must be a whole number.", "danger")
        return redirect(
            url_for("main.work_item_details", item_id=work_item.id)
        )

    if quantity_received < 0:
        flash("Received quantity cannot be negative.", "danger")

    elif quantity_received > part.quantity_ordered:
        flash(
            "Received quantity cannot exceed the quantity ordered.",
            "danger"
        )

    else:
        part.quantity_received = quantity_received

        # Generate notifications if status changes to Green.
        notify_when_green(work_item, previous_status)

        db.session.commit()

        flash(
            "Received quantity updated successfully!",
            "success"
        )

    return redirect(
        url_for("main.work_item_details", item_id=work_item.id)
    )


# Edit individual Part details (Part Number, Description, Notes, Quantities)
@main.route("/part/<int:part_id>/edit", methods=["GET", "POST"])
def edit_part(part_id):
    part = db.get_or_404(PartLine, part_id)

    if request.method == "POST":
        part_number = request.form.get("part_number", "").strip()
        description = request.form.get("description", "").strip()
        notes = request.form.get("notes", "").strip()

        try:
            quantity_ordered = int(
                request.form.get("quantity_ordered", "1")
            )
            quantity_received = int(
                request.form.get("quantity_received", "0")
            )
        except ValueError:
            flash("Quantities must be whole numbers.", "danger")
            return redirect(
                url_for("main.edit_part", part_id=part.id)
            )

        if not part_number or not description:
            flash("Part Number and Description are required.", "danger")

        elif quantity_ordered <= 0:
            flash("Quantity Ordered must be greater than zero.", "danger")

        elif quantity_received < 0 or quantity_received > quantity_ordered:
            flash(
                "Quantity Received must be between zero and Quantity Ordered.",
                "danger"
            )

        else:
            part.part_number = part_number
            part.description = description
            part.quantity_ordered = quantity_ordered
            part.quantity_received = quantity_received
            part.notes = notes

            db.session.commit()

            flash("Part updated successfully!", "success")

            return redirect(
                url_for(
                    "main.work_item_details",
                    item_id=part.parts_order.work_item_id
                )
            )

    return render_template("edit_part.html", part=part)


@main.route("/part/<int:part_id>/delete", methods=["POST"])
def delete_part(part_id):
    part = db.get_or_404(PartLine, part_id)

    # Remember the Work Item ID before deleting the part
    work_item_id = part.parts_order.work_item_id

    # Remember the Part Number for the confirmation message
    part_number = part.part_number

    # Delete only this PartLine
    db.session.delete(part)
    db.session.commit()

    flash(
        f"Part {part_number} deleted successfully!",
        "success"
    )

    return redirect(
        url_for(
            "main.work_item_details",
            item_id=work_item_id
        )
    )


# Edit Supplier Order details (Supplier, Order Number, Notes)
@main.route("/parts-order/<int:order_id>/edit", methods=["GET", "POST"])
def edit_parts_order(order_id):
    parts_order = db.get_or_404(PartsOrder, order_id)

    suppliers = Supplier.query.order_by(Supplier.name.asc()).all()

    if request.method == "POST":
        supplier = request.form.get("supplier", "").strip()
        order_number = request.form.get("order_number", "").strip()
        notes = request.form.get("notes", "").strip()

        if not supplier:
            flash("Supplier is required.", "danger")

        else:
            parts_order.supplier = supplier
            parts_order.order_number = order_number
            parts_order.notes = notes

            db.session.commit()

            flash("Supplier order updated successfully!", "success")

            return redirect(
                url_for(
                    "main.work_item_details",
                    item_id=parts_order.work_item_id
                )
            )

    return render_template(
        "edit_parts_order.html",
        parts_order=parts_order,
        suppliers=suppliers
    )


@main.route("/work-item/<int:item_id>/update-dashboard", methods=["POST"])
def update_work_item_dashboard(item_id):
    item = WorkItem.query.get_or_404(item_id)

    item.technician = request.form.get("technician", "").strip()
    item.notes = request.form.get("notes", "").strip()

    appointment_date = request.form.get("appointment_date", "").strip()

    if appointment_date:
        item.appointment_date = datetime.strptime(
            appointment_date,
            "%Y-%m-%d"
        ).date()
    else:
        item.appointment_date = None

    db.session.commit()

    flash(
        f"Work Item {item.number} updated successfully.",
        "success"
    )

    return redirect(url_for("main.dashboard"))


@main.route("/settings/app")
@login_required
def app_settings():
    technicians = Technician.query.order_by(
        Technician.name.asc()
    ).all()

    suppliers = Supplier.query.order_by(
        Supplier.name.asc()
    ).all()

    return render_template(
        "app_settings.html",
        technicians=technicians,
        suppliers=suppliers
    )


@main.route("/settings/notifications/delete-old", methods=["POST"])
@login_required
def delete_old_notifications():
    # Only administrators can permanently delete
    # notifications across all users.
    if not current_user.is_admin:
        abort(403)

    cutoff_date_string = request.form.get(
        "cutoff_date", ""
    ).strip()

    # Validate the selected date.
    try:
        cutoff_date = datetime.strptime(
            cutoff_date_string,
            "%Y-%m-%d"
        )
    except ValueError:
        flash("Please select a valid cutoff date.", "danger")
        return redirect(url_for("main.app_settings"))

    # Notifications are stored using UTC timestamps.
    # Delete anything before midnight UTC on the
    # selected date, across ALL users.
    deleted_count = (
        Notification.query
        .filter(Notification.created_at < cutoff_date)
        .delete(synchronize_session=False)
    )

    db.session.commit()

    flash(
        f"Successfully deleted {deleted_count} old "
        f"notification(s) across all users.",
        "success"
    )

    return redirect(url_for("main.app_settings"))


@main.route("/settings/technicians/add", methods=["POST"])
def add_technician():
    name = request.form.get("name", "").strip()

    if not name:
        flash("Please enter a technician name.", "warning")
        return redirect(url_for("main.app_settings"))

    existing_technician = Technician.query.filter_by(name=name).first()

    if existing_technician:
        flash("This technician already exists.", "warning")
        return redirect(url_for("main.app_settings"))

    technician = Technician(name=name)

    db.session.add(technician)
    db.session.commit()

    flash(f"Technician '{name}' added successfully.", "success")

    return redirect(url_for("main.app_settings"))


@main.route("/settings/technicians/delete/<int:technician_id>", methods=["POST"])
def delete_technician(technician_id):
    technician = Technician.query.get_or_404(technician_id)

    name = technician.name

    db.session.delete(technician)
    db.session.commit()

    flash(f"Technician '{name}' removed from the list.", "success")

    return redirect(url_for("main.app_settings"))


@main.route("/settings/suppliers")
def supplier_settings():
    return redirect(url_for("main.app_settings"))


@main.route("/settings/suppliers/add", methods=["POST"])
def add_supplier():
    name = request.form.get("name", "").strip()

    if not name:
        flash("Please enter a supplier name.", "warning")
        return redirect(url_for("main.supplier_settings"))

    existing_supplier = Supplier.query.filter_by(name=name).first()

    if existing_supplier:
        flash("This supplier already exists.", "warning")
        return redirect(url_for("main.supplier_settings"))

    supplier = Supplier(name=name)

    db.session.add(supplier)
    db.session.commit()

    flash(f"Supplier '{name}' added successfully.", "success")

    return redirect(url_for("main.supplier_settings"))


@main.route("/settings/suppliers/delete/<int:supplier_id>", methods=["POST"])
def delete_supplier(supplier_id):
    supplier = Supplier.query.get_or_404(supplier_id)

    name = supplier.name

    db.session.delete(supplier)
    db.session.commit()

    flash(f"Supplier '{name}' removed from the list.", "success")

    return redirect(url_for("main.supplier_settings"))


@main.route("/users")
@admin_required
def manage_users():
    users = User.query.order_by(User.username.asc()).all()

    return render_template(
        "manage_users.html",
        users=users
    )


@main.route("/users/create", methods=["POST"])
@admin_required
def create_user():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    role = request.form.get("role", "employee")

    if not username or not password:
        flash("Username and password are required.", "danger")
        return redirect(url_for("main.manage_users"))

    if len(username) > 80:
        flash("Username must be 80 characters or fewer.", "danger")
        return redirect(url_for("main.manage_users"))

    if len(password) < 4:
        flash("Password must be at least 4 characters.", "danger")
        return redirect(url_for("main.manage_users"))

    if role not in ("admin", "employee"):
        flash("Invalid user role.", "danger")
        return redirect(url_for("main.manage_users"))

    existing_user = User.query.filter_by(username=username).first()

    if existing_user:
        flash("That username already exists.", "danger")
        return redirect(url_for("main.manage_users"))

    new_user = User(
        username=username,
        role=role,
        is_active=True
    )

    new_user.set_password(password)

    db.session.add(new_user)
    db.session.commit()

    flash(f"User '{username}' created successfully.", "success")
    return redirect(url_for("main.manage_users"))


@main.route("/users/<int:user_id>/reset-password", methods=["POST"])
@admin_required
def reset_user_password(user_id):
    user = db.get_or_404(User, user_id)

    new_password = request.form.get("new_password", "")

    if len(new_password) < 4:
        flash("Password must be at least 4 characters.", "danger")
        return redirect(url_for("main.manage_users"))

    user.set_password(new_password)
    db.session.commit()

    flash(
        f"Password for '{user.username}' updated successfully.",
        "success"
    )

    return redirect(url_for("main.manage_users"))


@main.route("/users/<int:user_id>/change-role", methods=["POST"])
@admin_required
def change_user_role(user_id):
    user = db.get_or_404(User, user_id)

    new_role = request.form.get("role", "")

    if new_role not in ("admin", "employee"):
        flash("Invalid user role.", "danger")
        return redirect(url_for("main.manage_users"))

    # Prevent administrators from removing their own admin access
    if user.id == current_user.id and new_role != "admin":
        flash(
            "You cannot remove your own administrator privileges.",
            "danger"
        )
        return redirect(url_for("main.manage_users"))

    if user.role == new_role:
        flash("This user already has the selected role.", "warning")
        return redirect(url_for("main.manage_users"))

    user.role = new_role
    db.session.commit()

    flash(
        f"Role for '{user.username}' updated successfully.",
        "success"
    )

    return redirect(url_for("main.manage_users"))


@main.route("/users/<int:user_id>/toggle-active", methods=["POST"])
@admin_required
def toggle_user_active(user_id):
    user = db.get_or_404(User, user_id)

    # Prevent administrators from disabling their own account
    if user.id == current_user.id:
        flash(
            "You cannot deactivate your own account.",
            "danger"
        )
        return redirect(url_for("main.manage_users"))

    user.is_active = not user.is_active

    db.session.commit()

    if user.is_active:
        flash(
            f"User '{user.username}' activated successfully.",
            "success"
        )
    else:
        flash(
            f"User '{user.username}' deactivated successfully.",
            "success"
        )

    return redirect(url_for("main.manage_users"))


def get_receiving_status(work_item):
    total_ordered = sum(
        part.quantity_ordered
        for order in work_item.parts_orders
        for part in order.parts
    )

    total_received = sum(
        part.quantity_received
        for order in work_item.parts_orders
        for part in order.parts
    )

    if total_ordered == 0 or total_received == 0:
        return "Red"

    if total_received >= total_ordered:
        return "Green"

    return "Yellow"


def notify_when_green(work_item, previous_status):

    # Do not notify users about archived Work Items.
    if work_item.is_archived:
        return

    # Do not notify users about unverified Work Items.
    if work_item.requires_order_verification:
        return

    new_status = get_receiving_status(work_item)

    # Only notify when the receiving status changes to Green.
    if previous_status == "Green" or new_status != "Green":
        return

    active_users = User.query.filter_by(
        is_active=True
    ).all()

    for user in active_users:

        notification = Notification(
            user_id=user.id,
            work_item_id=work_item.id,
            message=(
                f"All parts received for {work_item.type} "
                f"{work_item.number}. Ready for scheduling."
            )
        )

        db.session.add(notification)


@main.app_context_processor
def inject_notification_count():
    unread_count = 0
    recent_notifications = []

    if current_user.is_authenticated:
        unread_count = Notification.query.filter_by(
            user_id=current_user.id,
            is_read=False
        ).count()

        recent_notifications = (
            Notification.query.filter_by(
                user_id=current_user.id
            )
            .order_by(
                Notification.created_at.desc(),
                Notification.id.desc()
            )
            .limit(5)
            .all()
        )

    return {
        "unread_notification_count": unread_count,
        "recent_notifications": recent_notifications
    }


@main.route("/notifications")
@login_required
def notifications():
    user_notifications = Notification.query.filter_by(
        user_id=current_user.id
    ).order_by(
        Notification.created_at.desc(),
        Notification.id.desc()
    ).all()

    return render_template(
        "notifications.html",
        notifications=user_notifications
    )


@main.route("/notifications/<int:notification_id>/read", methods=["POST"])
@login_required
def mark_notification_read(notification_id):
    notification = db.get_or_404(Notification, notification_id)

    # Users can only update their own notifications.
    if notification.user_id != current_user.id:
        abort(403)

    if not notification.is_read:
        notification.is_read = True
        db.session.commit()

    return redirect(url_for("main.notifications"))


@main.route("/notifications/<int:notification_id>/dismiss", methods=["POST"])
@login_required
def dismiss_notification(notification_id):
    notification = db.get_or_404(Notification, notification_id)

    # Users can only dismiss their own notifications.
    if notification.user_id != current_user.id:
        abort(403)

    # Permanently delete the notification.
    db.session.delete(notification)
    db.session.commit()

    # Return JSON for background JavaScript requests.
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        unread_count = Notification.query.filter_by(
            user_id=current_user.id,
            is_read=False
        ).count()

        return jsonify({
            "success": True,
            "unread_count": unread_count
        })

    # Normal form submission fallback.
    return redirect(url_for("main.notifications"))


@main.route("/notifications/<int:notification_id>/open", methods=["POST"])
@login_required
def open_notification(notification_id):
    notification = db.get_or_404(Notification, notification_id)

    # Make sure the notification belongs to the logged-in user.
    if notification.user_id != current_user.id:
        abort(403)

    work_item_id = notification.work_item_id

    # Mark the notification as read.
    if not notification.is_read:
        notification.is_read = True
        db.session.commit()

    # Open the associated work item.
    return redirect(
        url_for("main.work_item_details", item_id=work_item_id)
    )


@main.route("/notifications/check")
@login_required
def check_notifications():
    unread_notifications = (
        Notification.query.filter_by(
            user_id=current_user.id,
            is_read=False
        )
        .order_by(
            Notification.created_at.desc(),
            Notification.id.desc()
        )
        .all()
    )

    return jsonify({
        "unread_count": len(unread_notifications),
        "notifications": [
            {
                "id": notification.id,
                "message": notification.message,
                "work_item_id": notification.work_item_id
            }
            for notification in unread_notifications
        ]
    })


@main.route("/import-pbs-orders", methods=["POST"])
@login_required
def import_pbs_orders():
    uploaded_file = request.files.get("excel_file")

    if not uploaded_file or not uploaded_file.filename:
        flash("Please select a PBS Order Excel file.", "danger")
        return redirect(url_for("main.dashboard"))

    if not uploaded_file.filename.lower().endswith(".xlsx"):
        flash("Only Excel (.xlsx) files are supported.", "danger")
        return redirect(url_for("main.dashboard"))

    try:
        # Limit uploads to 10 MB.
        file_bytes = uploaded_file.stream.read(10 * 1024 * 1024 + 1)

        if len(file_bytes) > 10 * 1024 * 1024:
            raise ValueError("Excel file exceeds the 10 MB limit.")

        # Open the Excel workbook.
        workbook = load_workbook(
            io.BytesIO(file_bytes),
            read_only=True,
            data_only=True
        )

        try:
            worksheet = workbook.worksheets[0]

            # Convert Excel cell values into strings so that
            # the existing import logic can process them.
            rows = []

            for excel_row in worksheet.iter_rows(values_only=True):
                row = []

                for value in excel_row:
                    if value is None:
                        row.append("")
                    elif isinstance(value, float) and value.is_integer():
                        row.append(str(int(value)))
                    else:
                        row.append(str(value).strip())

                rows.append(row)

        finally:
            workbook.close()

        if len(rows) < 5:
            raise ValueError("The Excel file does not contain enough rows.")

        # Line 2 contains the PBS Order Number.
        order_header = rows[1][0].strip()

        if not order_header.lower().startswith("order #"):
            raise ValueError("PBS Order Number not found on line 2.")

        order_number = order_header.split("#", 1)[1].strip()

        if not order_number:
            raise ValueError("PBS Order Number is empty.")

        # Line 4 contains the column headings.
        headings = [
            heading.strip().lower()
            for heading in rows[3]
        ]

        required_columns = [
            "reference",
            "part number",
            "description",
            "customer name",
            "source",
            "qty"
        ]

        for column in required_columns:
            if column not in headings:
                raise ValueError(
                    f"Required Excel column is missing: {column}"
                )

        columns = {
            name: headings.index(name)
            for name in required_columns
        }


        # Combine customer names that PBS splits across rows.
        customer_column = columns["customer name"]
        reference_column = columns["reference"]
        part_column = columns["part number"]

        cleaned_rows = []
        previous_part_row = None

        for line_number, row in enumerate(rows[4:], start=5):
            nonempty_columns = [
                index
                for index, value in enumerate(row)
                if value.strip()
            ]

            # A customer continuation row has text only
            # in the Customer Name column.
            is_customer_continuation = (
                nonempty_columns == [customer_column]
            )

            if is_customer_continuation:
                if previous_part_row is None:
                    raise ValueError(
                        f"Line {line_number}: Customer name "
                        "continuation has no preceding part."
                    )

                additional_name = row[customer_column].strip()

                previous_part_row[customer_column] += (
                    " " + additional_name
                )

                continue

            cleaned_rows.append(row)

            # Only a valid-looking part row can receive
            # a customer name continuation.
            if (
                len(row) > max(reference_column, part_column)
                and row[reference_column].strip()
                and row[part_column].strip()
            ):
                previous_part_row = row
            else:
                previous_part_row = None

        # Replace the original data rows with cleaned rows.
        rows = rows[:4] + cleaned_rows

        # Group parts by Work Item Type, Number and Supplier.
        grouped_orders = defaultdict(list)
        customers = {}

        for line_number, row in enumerate(rows[4:], start=5):
            # Ignore blank lines and the report totals line.
            if not any(cell.strip() for cell in row):
                continue

            # Ignore stock orders, notes continuation rows
            # and other rows without a Work Item and Part Number.
            if (
                not row[columns["reference"]].strip()
                or not row[columns["part number"]].strip()
            ):
                continue

            def field(name):
                index = columns[name]
                return row[index].strip() if index < len(row) else ""

            reference = field("reference")
            part_number = field("part number")
            description = field("description")
            customer = field("customer name").upper()
            supplier = "GM"
            quantity_text = field("qty")

            if "#" not in reference:
                raise ValueError(
                    f"Line {line_number}: Invalid Reference: {reference}"
                )

            item_type, item_number = [
                value.strip()
                for value in reference.split("#", 1)
            ]

            valid_types = {
                "work order": "Work Order",
                "estimate": "Estimate",
                "invoice": "Invoice",
                "quote": "Quote"
            }

            item_type = valid_types.get(item_type.lower())

            if not item_type or not item_number:
                raise ValueError(
                    f"Line {line_number}: Invalid Work Item Reference."
                )

            if not all([
                part_number,
                description,
                customer,
                supplier,
                quantity_text
            ]):
                raise ValueError(
                    f"Line {line_number}: Required part information is missing."
                )

            try:
                quantity_value = float(quantity_text)

                if (
                    not quantity_value.is_integer()
                    or quantity_value <= 0
                ):
                    raise ValueError()

                quantity = int(quantity_value)

            except ValueError:
                raise ValueError(
                    f"Line {line_number}: Invalid quantity: {quantity_text}"
                )

            key = (item_type, item_number, supplier)

            # A Work Item should have a consistent customer.
            customer_key = (item_type, item_number)

            if (
                customer_key in customers
                and customers[customer_key] != customer
            ):
                raise ValueError(
                    f"Line {line_number}: Conflicting customer names "
                    f"for {item_type} #{item_number}."
                )

            customers[customer_key] = customer

            grouped_orders[key].append({
                "part_number": part_number,
                "description": description,
                "quantity_ordered": quantity
            })

        if not grouped_orders:
            raise ValueError("No customer-ordered parts were found in the Excel file.")

        created_items = 0
        created_orders = 0
        created_parts = 0
        skipped_orders = 0

        reconciled_orders = 0
        updated_customers = 0
        updated_descriptions = 0

        warnings = []

        # Process each grouped GM Supplier Order.
        for (item_type, item_number, supplier), parts in grouped_orders.items():

            identifier = (
                f"{item_type} #{item_number}, "
                f"GM Order #{order_number}"
            )

            # Find the matching Work Item.
            work_item = WorkItem.query.filter_by(
                number=item_number,
                type=item_type
            ).first()

            # Create the Work Item if it does not exist.
            if not work_item:

                work_item = WorkItem(
                    number=item_number,
                    type=item_type,
                    customer=customers[(item_type, item_number)],
                    technician=None,
                    notes="",
                    requires_order_verification=False
                )

                db.session.add(work_item)
                db.session.flush()

                created_items += 1

            # Record the original status and verification flag.
            previous_status = get_receiving_status(work_item)

            was_unverified = (
                work_item.requires_order_verification
            )

            # Find the matching GM Supplier Order.
            matching_orders = [
                order
                for order in work_item.parts_orders
                if (
                    order.supplier.strip().upper() == "GM"
                    and (order.order_number or "").strip()
                    == order_number
                )
            ]

            # Do not guess when multiple orders match.
            if len(matching_orders) > 1:

                warnings.append(
                    f"{identifier}: Multiple matching GM "
                    "Supplier Orders found. "
                    "Manual review required."
                )

                skipped_orders += 1
                continue

            # Replace the placeholder customer name.
            if work_item.customer.strip().upper() == "<IMPORT CREATED>":

                work_item.customer = customers[
                    (item_type, item_number)
                ]

                updated_customers += 1

            # Handle an existing Supplier Order.
            if matching_orders:

                parts_order = matching_orders[0]

                # Skip orders that have already been verified.
                if not parts_order.created_from_receipt:

                    skipped_orders += 1
                    continue

                # Prepare incoming and existing part mappings.
                incoming_parts = defaultdict(list)
                existing_parts = defaultdict(list)

                for part_data in parts:

                    normalized_number = (
                        part_data["part_number"].strip().upper()
                    )

                    incoming_parts[normalized_number].append(
                        part_data
                    )

                for part in parts_order.parts:

                    normalized_number = (
                        part.part_number.strip().upper()
                    )

                    existing_parts[normalized_number].append(
                        part
                    )

                reconciliation_errors = []

                # Check for duplicate incoming part numbers.
                for part_number, matches in incoming_parts.items():

                    if len(matches) > 1:

                        reconciliation_errors.append(
                            f"{identifier}, Part #{part_number}: "
                            "Multiple matching parts in the "
                            "PBS Order Report."
                        )

                # Check existing receipt-created parts.
                for part_number, matches in existing_parts.items():

                    if len(matches) > 1:

                        reconciliation_errors.append(
                            f"{identifier}, Part #{part_number}: "
                            "Multiple matching parts in PartsTrack."
                        )

                        continue

                    if part_number not in incoming_parts:

                        reconciliation_errors.append(
                            f"{identifier}, Part #{part_number}: "
                            "Existing part was not found in "
                            "the PBS Order Report."
                        )

                        continue

                    if len(incoming_parts[part_number]) != 1:
                        continue

                    existing_part = matches[0]
                    part_data = incoming_parts[part_number][0]

                    # Do not automatically change conflicting
                    # ordered quantities.
                    if (
                        existing_part.quantity_ordered
                        != part_data["quantity_ordered"]
                    ):

                        reconciliation_errors.append(
                            f"{identifier}, Part #{part_number}: "
                            f"PBS ordered quantity "
                            f"({part_data['quantity_ordered']}) "
                            f"differs from PartsTrack "
                            f"({existing_part.quantity_ordered})."
                        )

                    if (
                        existing_part.quantity_received
                        > part_data["quantity_ordered"]
                    ):

                        reconciliation_errors.append(
                            f"{identifier}, Part #{part_number}: "
                            "Received quantity exceeds the "
                            "PBS ordered quantity."
                        )

                # Do not partially reconcile an order
                # containing conflicting information.
                if reconciliation_errors:

                    warnings.extend(reconciliation_errors)

                    work_item.requires_order_verification = True

                    skipped_orders += 1
                    continue

                # Reconcile the original Order Report.
                for part_number, matches in incoming_parts.items():

                    part_data = matches[0]

                    if part_number in existing_parts:

                        part = existing_parts[part_number][0]

                        # Populate missing descriptions only.
                        if not (part.description or "").strip():

                            part.description = part_data[
                                "description"
                            ]

                            updated_descriptions += 1

                        # Existing received quantities
                        # remain unchanged.

                    else:

                        # Add parts missing from the receipt.
                        part = PartLine(
                            parts_order=parts_order,
                            part_number=part_data["part_number"],
                            description=part_data["description"],
                            quantity_ordered=part_data[
                                "quantity_ordered"
                            ],
                            quantity_received=0,
                            notes=""
                        )

                        db.session.add(part)

                        created_parts += 1

                # Mark this Supplier Order as verified.
                parts_order.created_from_receipt = False

                reconciled_orders += 1

            else:

                # Create a normal GM Supplier Order.
                parts_order = PartsOrder(
                    work_item=work_item,
                    supplier="GM",
                    order_number=order_number,
                    notes="",
                    created_from_receipt=False
                )

                db.session.add(parts_order)

                created_orders += 1

                # Add all ordered parts.
                for part_data in parts:

                    part = PartLine(
                        parts_order=parts_order,
                        part_number=part_data["part_number"],
                        description=part_data["description"],
                        quantity_ordered=part_data[
                            "quantity_ordered"
                        ],
                        quantity_received=0,
                        notes=""
                    )

                    db.session.add(part)

                    created_parts += 1

            db.session.flush()

            # Check whether any Supplier Orders still
            # require verification.
            work_item.requires_order_verification = any(
                order.created_from_receipt
                for order in work_item.parts_orders
            )

            # Generate a notification if verification is
            # complete and all ordered parts are received.
            if (
                was_unverified
                and not work_item.requires_order_verification
                and not work_item.is_archived
            ):

                # Treat an unverified Work Item as not
                # previously ready for scheduling.
                notify_when_green(work_item, "Red")

            elif (
                not work_item.requires_order_verification
                and not work_item.is_archived
            ):

                notify_when_green(
                    work_item,
                    previous_status
                )

        # Save all changes together.
        db.session.commit()

        flash(
            f"PBS Order #{order_number} processed successfully. "
            f"New Work Items: {created_items}, "
            f"New Supplier Orders: {created_orders}, "
            f"New Parts: {created_parts}, "
            f"Reconciled Orders: {reconciled_orders}, "
            f"Updated Customers: {updated_customers}, "
            f"Updated Descriptions: {updated_descriptions}, "
            f"Skipped Orders: {skipped_orders}, "
            f"Warnings: {len(warnings)}.",
            "success" if not warnings else "warning"
        )

        # Display reconciliation warnings.
        for warning in warnings:
            flash(warning, "warning")

    except (ValueError, InvalidFileException, BadZipFile) as error:
        db.session.rollback()
        flash(f"PBS import failed: {error}", "danger")

    except Exception:
        db.session.rollback()
        current_app.logger.exception("PBS Order Import failed")
        flash(
            "An unexpected error occurred while importing the PBS order.",
            "danger"
        )

    return redirect(url_for("main.dashboard"))


def read_pbs_receipt(file_bytes):

    workbook = load_workbook(
        io.BytesIO(file_bytes),
        read_only=True,
        data_only=True
    )

    try:
        worksheet = workbook.worksheets[0]

        rows = list(
            worksheet.iter_rows(values_only=True)
        )

    finally:
        workbook.close()

    if len(rows) < 6:
        raise ValueError(
            "The Excel file does not contain enough rows."
        )

    def cell_text(value):
        if value is None:
            return ""

        if isinstance(value, float) and value.is_integer():
            return str(int(value))

        return str(value).strip()

    # Extract receipt information from row 4.
    receipt_header = cell_text(rows[3][0])

    header_match = re.search(
        r"Receipt:\s*(.*?)\s+Received:\s*"
        r"(\d{1,2}/\d{1,2}/\d{4})",
        receipt_header,
        re.IGNORECASE
    )

    if not header_match:
        raise ValueError(
            "PBS Receipt information was not found."
        )

    receipt_name = header_match.group(1).strip()

    receipt_date = datetime.strptime(
        header_match.group(2),
        "%m/%d/%Y"
    ).date()

    # Row 5 contains the column headings.
    headings = [
        cell_text(value).lower()
        for value in rows[4]
    ]

    required_columns = [
        "order #",
        "part number",
        "type",
        "reference",
        "ordered",
        "receipted",
        "cancelled"
    ]

    for column in required_columns:
        if column not in headings:
            raise ValueError(
                f"Required Excel column is missing: {column}"
            )

    columns = {
        name: headings.index(name)
        for name in required_columns
    }

    # Convert PBS reference types to PartsTrack types.
    valid_types = {
        "est": "Estimate",
        "estimate": "Estimate",
        "inv": "Invoice",
        "invoice": "Invoice",
        "wo": "Work Order",
        "ro": "Work Order",
        "work order": "Work Order",
        "quote": "Quote",
        "quo": "Quote",
        "qt": "Quote"
    }

    records = []

    for line_number, row in enumerate(rows[5:], start=6):

        def field(name):
            index = columns[name]

            if index >= len(row):
                return ""

            return cell_text(row[index])

        # Only process customer-ordered SOP parts.
        if field("type").upper() != "SOP":
            continue

        order_number = field("order #")
        part_number = field("part number").upper()
        reference = field("reference")

        if not order_number:
            raise ValueError(
                f"Row {line_number}: Missing Order Number."
            )        

        if not part_number or ":" not in reference:
            raise ValueError(
                f"Row {line_number}: Invalid part or reference."
            )

        reference_type, item_number = [
            value.strip()
            for value in reference.split(":", 1)
        ]

        item_type = valid_types.get(
            reference_type.lower()
        )

        if not item_type or not item_number:
            raise ValueError(
                f"Row {line_number}: Invalid Work Item "
                f"Reference: {reference}"
            )

        def read_quantity(name):
            value = field(name)

            try:
                quantity = Decimal(value)

                if (
                    not quantity.is_finite()
                    or quantity < 0
                    or quantity != quantity.to_integral_value()
                ):
                    raise ValueError()

                return int(quantity)

            except (InvalidOperation, ValueError):
                raise ValueError(
                    f"Row {line_number}: Invalid "
                    f"{name} quantity: {value}"
                )

        quantity_ordered = read_quantity("ordered")
        quantity_receipted = read_quantity("receipted")
        quantity_cancelled = read_quantity("cancelled")

        records.append({
            "line_number": line_number,
            "order_number": order_number,
            "item_type": item_type,
            "item_number": item_number,
            "part_number": part_number,
            "quantity_ordered": quantity_ordered,
            "quantity_receipted": quantity_receipted,
            "quantity_cancelled": quantity_cancelled
        })

    if not records:
        raise ValueError(
            "No SOP parts were found in the Receipt Report."
        )

    return receipt_name, receipt_date, records


def generate_receipt_fingerprint(receipt_date, records):

    normalized_records = []

    for record in records:
        normalized_records.append({
            "order_number": record["order_number"].strip(),
            "item_type": record["item_type"].strip().upper(),
            "item_number": record["item_number"].strip(),
            "part_number": record["part_number"].strip().upper(),
            "quantity_ordered": record["quantity_ordered"],
            "quantity_receipted": record["quantity_receipted"],
            "quantity_cancelled": record["quantity_cancelled"]
        })

    normalized_records.sort(
        key=lambda record: (
            record["order_number"],
            record["item_type"],
            record["item_number"],
            record["part_number"],
            record["quantity_ordered"],
            record["quantity_receipted"],
            record["quantity_cancelled"]
        )
    )

    fingerprint_data = {
        "receipt_date": receipt_date.isoformat(),
        "records": normalized_records
    }

    serialized_data = json.dumps(
        fingerprint_data,
        sort_keys=True,
        separators=(",", ":")
    )

    return hashlib.sha256(
        serialized_data.encode("utf-8")
    ).hexdigest()


@main.route("/import-pbs-receipts", methods=["POST"])
@login_required
def import_pbs_receipts():

    uploaded_file = request.files.get("excel_file")

    if not uploaded_file or not uploaded_file.filename:
        flash("Please select a PBS Receipt Excel file.", "danger")
        return redirect(url_for("main.dashboard"))

    if not uploaded_file.filename.lower().endswith(".xlsx"):
        flash("Only Excel (.xlsx) files are supported.", "danger")
        return redirect(url_for("main.dashboard"))

    try:
        # Limit uploads to 10 MB.
        file_bytes = uploaded_file.stream.read(
            10 * 1024 * 1024 + 1
        )

        if len(file_bytes) > 10 * 1024 * 1024:
            raise ValueError(
                "Excel file exceeds the 10 MB limit."
            )

        # Read and validate the Receipt Report.
        receipt_name, receipt_date, records = read_pbs_receipt(
            file_bytes
        )

        # Generate the unique receipt fingerprint.
        fingerprint = generate_receipt_fingerprint(
            receipt_date,
            records
        )

        # Check whether this receipt has already been imported.
        existing_receipt = ReceiptImport.query.filter_by(
            fingerprint=fingerprint
        ).first()

        if existing_receipt:
            flash(
                f"This receipt has already been imported "
                f"by {existing_receipt.imported_by} on "
                f"{existing_receipt.imported_at:%Y-%m-%d %H:%M} UTC. "
                "No quantities were updated.",
                "warning"
            )

            return redirect(url_for("main.dashboard"))

        warnings = []
        updated_part_ids = set()
        affected_work_items = {}

        work_items_created = 0
        supplier_orders_created = 0
        part_lines_created = 0

        skipped = 0
        total_received = 0

        # Register the receipt within the same transaction.
        receipt_import = ReceiptImport(
            receipt_name=receipt_name,
            receipt_date=receipt_date,
            fingerprint=fingerprint,
            filename=uploaded_file.filename,
            imported_by=current_user.username,
            parts_updated=0
        )

        db.session.add(receipt_import)
        db.session.flush()

        # Process each SOP receipt record.
        for record in records:

            item_type = record["item_type"]
            item_number = record["item_number"]
            order_number = record["order_number"]
            part_number = record["part_number"]

            quantity_ordered = record["quantity_ordered"]
            quantity_receipted = record["quantity_receipted"]
            quantity_cancelled = record["quantity_cancelled"]

            identifier = (
                f"{item_type} #{item_number}, "
                f"GM Order #{order_number}, "
                f"Part #{part_number}"
            )

            # Warn about cancellations.
            if quantity_cancelled > 0:
                warnings.append(
                    f"{identifier}: PBS reports "
                    f"{quantity_cancelled} cancelled. "
                    "Ordered quantity was not changed."
                )

            # Validate quantities before creating records.
            if quantity_ordered <= 0:
                warnings.append(
                    f"{identifier}: Invalid ordered quantity."
                )

                skipped += 1
                continue

            if quantity_receipted > quantity_ordered:
                warnings.append(
                    f"{identifier}: Receipted quantity exceeds "
                    "the PBS ordered quantity."
                )

                skipped += 1
                continue

            # Find the matching Work Item.
            work_item = WorkItem.query.filter_by(
                number=item_number,
                type=item_type
            ).first()

            # Create the Work Item if it does not exist.
            if not work_item:

                work_item = WorkItem(
                    number=item_number,
                    type=item_type,
                    customer="<Import Created>",
                    requires_order_verification=True,
                    is_archived=False
                )

                db.session.add(work_item)
                db.session.flush()

                work_items_created += 1

            # Record the original receiving status before
            # making any changes to the Work Item.
            if work_item.id not in affected_work_items:

                affected_work_items[work_item.id] = (
                    work_item,
                    get_receiving_status(work_item)
                )

            # Find the matching GM Supplier Order.
            matching_orders = [
                order
                for order in work_item.parts_orders
                if (
                    order.supplier.strip().upper() == "GM"
                    and (order.order_number or "").strip()
                    == order_number
                )
            ]

            # Do not guess when multiple orders match.
            if len(matching_orders) > 1:

                warnings.append(
                    f"{identifier}: Multiple matching GM "
                    "Supplier Orders found. "
                    "Manual review required."
                )

                skipped += 1
                continue

            # Create a missing GM Supplier Order.
            if not matching_orders:

                parts_order = PartsOrder(
                    work_item=work_item,
                    supplier="GM",
                    order_number=order_number,
                    created_from_receipt=True
                )

                db.session.add(parts_order)
                db.session.flush()

                work_item.requires_order_verification = True

                supplier_orders_created += 1

            else:

                parts_order = matching_orders[0]

            # Find the part within the matching GM order.
            matching_parts = [
                part
                for part in parts_order.parts
                if (
                    part.part_number.strip().upper()
                    == part_number.strip().upper()
                )
            ]

            # Do not guess when multiple parts match.
            if len(matching_parts) > 1:

                warnings.append(
                    f"{identifier}: Multiple matching parts "
                    "found. Manual review required."
                )

                skipped += 1
                continue

            # Create a missing Part Line.
            if not matching_parts:

                part = PartLine(
                    parts_order=parts_order,
                    part_number=part_number,
                    description="",
                    quantity_ordered=quantity_ordered,
                    quantity_received=0
                )

                db.session.add(part)
                db.session.flush()

                parts_order.created_from_receipt = True
                work_item.requires_order_verification = True

                part_lines_created += 1

            else:

                part = matching_parts[0]

            # Compare the ordered quantities.
            if quantity_ordered != part.quantity_ordered:

                # Require verification before allowing
                # ready-for-scheduling notifications.
                parts_order.created_from_receipt = True
                work_item.requires_order_verification = True

                warnings.append(
                    f"{identifier}: PBS ordered quantity "
                    f"({quantity_ordered}) differs from "
                    f"PartsTrack ({part.quantity_ordered}). "
                    "Order verification required. "
                    "Ordered quantity was not changed."
                )

            # Nothing to receive on this record.
            if quantity_receipted == 0:
                continue

            # Calculate the new received quantity.
            new_quantity_received = (
                part.quantity_received + quantity_receipted
            )

            # Prevent receiving more than was ordered.
            if new_quantity_received > part.quantity_ordered:

                warnings.append(
                    f"{identifier}: Receiving "
                    f"{quantity_receipted} additional part(s) "
                    "would exceed the ordered quantity. "
                    f"Currently received: "
                    f"{part.quantity_received}, "
                    f"Ordered: {part.quantity_ordered}. "
                    "Part was not updated."
                )

                skipped += 1
                continue

            # Apply the received quantity.
            part.quantity_received = new_quantity_received

            updated_part_ids.add(part.id)
            total_received += quantity_receipted

        # Complete the receipt import history.
        receipt_import.parts_updated = len(updated_part_ids)

        receipt_import.warnings = (
            "\n".join(warnings) if warnings else None
        )

        # Generate notifications only for verified Work Items.
        for work_item, previous_status in affected_work_items.values():

            if work_item.requires_order_verification:
                continue

            notify_when_green(work_item, previous_status)

        # Save receiving updates, notifications and
        # receipt history together.
        db.session.commit()

        flash(
            f"PBS Receipt '{receipt_name}' processed successfully. "
            f"Work Items created: {work_items_created}, "
            f"Supplier Orders created: {supplier_orders_created}, "
            f"Part Lines created: {part_lines_created}, "
            f"Parts received: {len(updated_part_ids)}, "
            f"Total quantity received: {total_received}, "
            f"Skipped records: {skipped}, "
            f"Warnings: {len(warnings)}.",
            "success" if not warnings else "warning"
        )

        # Display the first 10 warnings on the dashboard.
        for warning in warnings[:10]:
            flash(warning, "warning")

        if len(warnings) > 10:
            flash(
                f"{len(warnings) - 10} additional warnings "
                "were saved in the receipt import history.",
                "warning"
            )

    except (ValueError, InvalidFileException, BadZipFile) as error:

        db.session.rollback()

        flash(
            f"PBS Receipt Import failed: {error}",
            "danger"
        )

    except IntegrityError:

        db.session.rollback()

        flash(
            "The receipt could not be saved because of a "
            "database constraint conflict. It may have "
            "already been imported by another user. "
            "No receiving changes were saved.",
            "warning"
        )

    except Exception:

        db.session.rollback()

        current_app.logger.exception(
            "PBS Receipt Import failed"
        )

        flash(
            "An unexpected error occurred while "
            "importing the PBS receipt.",
            "danger"
        )

    return redirect(url_for("main.dashboard"))

@main.route("/receipt-import-history")
@login_required
def receipt_import_history():

    # Get search and filter values.
    search_query = request.args.get("search", "").strip()
    receipt_date_filter = request.args.get("receipt_date", "").strip()
    warnings_only = request.args.get("warnings_only") == "1"
    page = request.args.get("page", 1, type=int)

    # Calculate overall statistics.
    total_imports = ReceiptImport.query.count()

    imports_with_warnings = ReceiptImport.query.filter(
        ReceiptImport.warnings.isnot(None),
        ReceiptImport.warnings != ""
    ).count()

    successful_imports = total_imports - imports_with_warnings

    # Build the history query.
    query = ReceiptImport.query

    # Search by receipt name, filename or username.
    if search_query:
        search_pattern = f"%{search_query}%"

        query = query.filter(
            db.or_(
                ReceiptImport.receipt_name.ilike(search_pattern),
                ReceiptImport.filename.ilike(search_pattern),
                ReceiptImport.imported_by.ilike(search_pattern)
            )
        )

    # Filter by PBS receipt date.
    if receipt_date_filter:
        try:
            selected_date = date.fromisoformat(
                receipt_date_filter
            )

            query = query.filter(
                ReceiptImport.receipt_date == selected_date
            )

        except ValueError:
            flash("Invalid receipt date.", "warning")

            return redirect(
                url_for("main.receipt_import_history")
            )

    # Show only imports containing warnings.
    if warnings_only:
        query = query.filter(
            ReceiptImport.warnings.isnot(None),
            ReceiptImport.warnings != ""
        )

    # Display newest imports first.
    pagination = query.order_by(
        ReceiptImport.imported_at.desc(),
        ReceiptImport.id.desc()
    ).paginate(
        page=max(page, 1),
        per_page=25,
        error_out=False
    )

    receipt_imports = pagination.items

    return render_template(
        "receipt_import_history.html",
        receipt_imports=receipt_imports,
        pagination=pagination,
        total_imports=total_imports,
        successful_imports=successful_imports,
        imports_with_warnings=imports_with_warnings,
        search_query=search_query,
        receipt_date_filter=receipt_date_filter,
        warnings_only=warnings_only
    )