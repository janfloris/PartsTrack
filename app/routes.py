from flask import Blueprint, render_template

main = Blueprint("main", __name__)


@main.route("/")
def dashboard():

    work_items = [
        {
            "number": "105432",
            "type": "Work Order",
            "customer": "John Smith",
            "parts_ordered": 4,
            "parts_received": 4,
            "status": "Green"
        },
        {
            "number": "205123",
            "type": "Estimate",
            "customer": "Jane Doe",
            "parts_ordered": 6,
            "parts_received": 3,
            "status": "Yellow"
        },
        {
            "number": "305123",
            "type": "Invoice",
            "customer": "Fleet Customer",
            "parts_ordered": 2,
            "parts_received": 0,
            "status": "Red"
        },
        {
            "number": "405123",
            "type": "Quote",
            "customer": "Customer A",
            "parts_ordered": 5,
            "parts_received": 1,
            "status": "Yellow"
        },
        {
            "number": "105433",
            "type": "Work Order",
            "customer": "Customer B",
            "parts_ordered": 3,
            "parts_received": 0,
            "status": "Red"
        }
    ]

    total_items = len(work_items)

    green_count = sum(
        1 for item in work_items
        if item["status"] == "Green"
    )

    yellow_count = sum(
        1 for item in work_items
        if item["status"] == "Yellow"
    )

    red_count = sum(
        1 for item in work_items
        if item["status"] == "Red"
    )

    return render_template(
        "dashboard.html",
        work_items=work_items,
        total_items=total_items,
        green_count=green_count,
        yellow_count=yellow_count,
        red_count=red_count
    )