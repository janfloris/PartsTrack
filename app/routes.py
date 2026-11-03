
from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    request,
    flash
)

from app import db
from app.models import WorkItem

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
