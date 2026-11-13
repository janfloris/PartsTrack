
from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    request,
    flash,
    abort
)

from app import db
from flask_login import (
    current_user,
    login_user,
    logout_user,
    login_required
)
from app.models import WorkItem, PartsOrder, PartLine, Technician, Supplier, User, Notification 
from datetime import date, datetime
from functools import wraps
from flask import abort, jsonify

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

    # Calculate receiving status and counts for all active Work Items
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

        if total_ordered == 0 or total_received == 0:
            item.receiving_status = "Red"

        elif total_received >= total_ordered:
            item.receiving_status = "Green"

        else:
            item.receiving_status = "Yellow"

        if item.receiving_status == "Green":
            green_count += 1

        elif item.receiving_status == "Yellow":
            yellow_count += 1

        else:
            red_count += 1

    # Get search and status filter values
    search_query = request.args.get("search", "").strip().lower()
    status_filter = request.args.get("status", "").strip()

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

    # Filter Work Items by receiving status
    if status_filter in ["Red", "Yellow", "Green"]:
        filtered_items = [
            item for item in filtered_items
            if item.receiving_status == status_filter
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
        search_query=search_query,
        status_filter=status_filter,
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

@main.route("/new-work-item", methods=["GET", "POST"])
def new_work_item():
    suppliers = Supplier.query.order_by(Supplier.name.asc()).all()

    if request.method == "POST":
        number = request.form.get("number", "").strip()
        item_type = request.form.get("type", "").strip()
        customer = request.form.get("customer", "").strip()
        technician = request.form.get("technician", "").strip()
        notes = request.form.get("notes", "").strip()

        if not number or not item_type or not customer:
            flash(
                "Work Item Number, Type, and Customer are required.",
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

@main.route("/work-item/<int:item_id>/add-order", methods=["POST"])
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


    if request.method == "POST":
        number = request.form.get("number", "").strip()
        item_type = request.form.get("type", "").strip()
        customer = request.form.get("customer", "").strip()
        technician = request.form.get("technician", "").strip()
        notes = request.form.get("notes", "").strip()

        if not number or not item_type or not customer:
            flash(
                "Work Item Number, Type, and Customer are required.",
                "danger"
            )
            return redirect(url_for("main.new_work_item"))

        work_item = WorkItem(
            number=number,
            type=item_type,
            customer=customer,
            technician=technician,
            notes=notes
        )

        db.session.add(work_item)
        db.session.commit()

        flash("Work Item created successfully!", "success")

        return redirect(url_for("main.dashboard"))

    return render_template("new_work_item.html")

@main.route("/archive/<int:item_id>", methods=["POST"])
def archive_work_item(item_id):
    work_item = db.session.get(WorkItem, item_id)

    if work_item:
        work_item.is_archived = True
        db.session.commit()
        flash("Work Item archived successfully.", "success")

    return redirect(url_for("main.dashboard"))

@main.route("/archive")
def archived_work_items():
    work_items = (
        WorkItem.query
        .filter_by(is_archived=True)
        .order_by(WorkItem.created_at.desc())
        .all()
    )

    return render_template(
        "archive.html",
        work_items=work_items
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


@main.route("/settings/technicians")
@login_required
def technician_settings():
    technicians = Technician.query.order_by(
        Technician.name.asc()
    ).all()

    suppliers = Supplier.query.order_by(
        Supplier.name.asc()
    ).all()

    return render_template(
        "technician_settings.html",
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
        return redirect(url_for("main.technician_settings"))

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

    return redirect(url_for("main.technician_settings"))


@main.route("/settings/technicians/add", methods=["POST"])
def add_technician():
    name = request.form.get("name", "").strip()

    if not name:
        flash("Please enter a technician name.", "warning")
        return redirect(url_for("main.technician_settings"))

    existing_technician = Technician.query.filter_by(name=name).first()

    if existing_technician:
        flash("This technician already exists.", "warning")
        return redirect(url_for("main.technician_settings"))

    technician = Technician(name=name)

    db.session.add(technician)
    db.session.commit()

    flash(f"Technician '{name}' added successfully.", "success")

    return redirect(url_for("main.technician_settings"))


@main.route("/settings/technicians/delete/<int:technician_id>", methods=["POST"])
def delete_technician(technician_id):
    technician = Technician.query.get_or_404(technician_id)

    name = technician.name

    db.session.delete(technician)
    db.session.commit()

    flash(f"Technician '{name}' removed from the list.", "success")

    return redirect(url_for("main.technician_settings"))


@main.route("/settings/suppliers")
def supplier_settings():
    return redirect(url_for("main.technician_settings"))


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
    new_status = get_receiving_status(work_item)

    # Notify only when the work item changes to Green.
    if previous_status == "Green" or new_status != "Green":
        return

    active_users = User.query.filter_by(is_active=True).all()

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
