
from flask import Blueprint, render_template, redirect, url_for, session

main = Blueprint("main", __name__)


# Sample work items
work_items = [
    {
        "number": "105432",
        "type": "Work Order",
        "customer": "John Smith",
        "technician": "Mike",
        "parts_ordered": 4,
        "parts_received": 4,
        "status": "Green",
        "notes": "All parts received. Ready for repair."
    },
    {
        "number": "205123",
        "type": "Estimate",
        "customer": "Jane Doe",
        "technician": "David",
        "parts_ordered": 6,
        "parts_received": 3,
        "status": "Yellow",
        "notes": "Waiting for remaining parts from GM."
    },
    {
        "number": "305123",
        "type": "Invoice",
        "customer": "Fleet Customer",
        "technician": "Chris",
        "parts_ordered": 2,
        "parts_received": 0,
        "status": "Red",
        "notes": "Parts have been ordered."
    },
    {
        "number": "405123",
        "type": "Quote",
        "customer": "Customer A",
        "technician": "Mike",
        "parts_ordered": 5,
        "parts_received": 1,
        "status": "Yellow",
        "notes": "Customer waiting for vehicle repair."
    },
    {
        "number": "105433",
        "type": "Work Order",
        "customer": "Customer B",
        "technician": "David",
        "parts_ordered": 3,
        "parts_received": 0,
        "status": "Red",
        "notes": "Nothing received yet."
    }
]


@main.route("/")
def dashboard():

    archived_items = session.get("archived_items", [])

    active_work_items = [
        item for item in work_items
        if item["number"] not in archived_items
    ]

    total_items = len(active_work_items)

    green_count = sum(
        1 for item in active_work_items
        if item["status"] == "Green"
    )

    yellow_count = sum(
        1 for item in active_work_items
        if item["status"] == "Yellow"
    )

    red_count = sum(
        1 for item in active_work_items
        if item["status"] == "Red"
    )

    return render_template(
        "dashboard.html",
        work_items=active_work_items,
        total_items=total_items,
        green_count=green_count,
        yellow_count=yellow_count,
        red_count=red_count
    )


@main.route("/archive/<work_item_number>", methods=["POST"])
def archive_work_item(work_item_number):

    archived_items = session.get("archived_items", [])

    if work_item_number not in archived_items:
        archived_items.append(work_item_number)

    session["archived_items"] = archived_items

    return redirect(url_for("main.dashboard"))
