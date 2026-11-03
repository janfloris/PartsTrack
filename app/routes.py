
from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    request,
    flash
)

from app import db
from app.models import WorkItem, PartsOrder, PartLine

main = Blueprint("main", __name__)



@main.route("/")
def dashboard():
    work_items = WorkItem.query.filter_by(
        is_archived=False
    ).order_by(WorkItem.created_at.desc()).all()

    total_items = len(work_items)

    green_count = 0
    yellow_count = 0
    red_count = 0

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

    return render_template(
        "dashboard.html",
        work_items=work_items,
        total_items=total_items,
        green_count=green_count,
        yellow_count=yellow_count,
        red_count=red_count
    )


@main.route("/work-item/<int:item_id>")
def work_item_details(item_id):
    work_item = db.get_or_404(WorkItem, item_id)

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
        status=status
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

@main.route("/new-work-item", methods=["GET", "POST"])
def new_work_item():
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

    try:
        quantity_received = int(
            request.form.get("quantity_received", "0")
        )
    except ValueError:
        flash("Received quantity must be a whole number.", "danger")
        return redirect(
            url_for(
                "main.work_item_details",
                item_id=part.parts_order.work_item_id
            )
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
        db.session.commit()

        flash("Received quantity updated successfully!", "success")

    return redirect(
        url_for(
            "main.work_item_details",
            item_id=part.parts_order.work_item_id
        )
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
        parts_order=parts_order
    )
