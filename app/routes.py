
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

    return render_template(
        "dashboard.html",
        work_items=work_items,
        total_items=total_items
    )

@main.route("/work-item/<int:item_id>")
def work_item_details(item_id):
    work_item = db.get_or_404(WorkItem, item_id)

    return render_template(
        "work_item_details.html",
        work_item=work_item
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
