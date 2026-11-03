
from datetime import datetime, timezone

from app import db


class WorkItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    number = db.Column(db.String(50), nullable=False)
    type = db.Column(db.String(50), nullable=False)
    customer = db.Column(db.String(150), nullable=False)
    technician = db.Column(db.String(100), nullable=True)
    notes = db.Column(db.Text, nullable=True)

    is_archived = db.Column(
        db.Boolean,
        default=False,
        nullable=False
    )

    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    parts_orders = db.relationship(
        "PartsOrder",
        backref="work_item",
        cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<WorkItem {self.number}>"


class PartsOrder(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    work_item_id = db.Column(
        db.Integer,
        db.ForeignKey("work_item.id"),
        nullable=False
    )

    supplier = db.Column(
        db.String(150),
        nullable=False
    )

    order_number = db.Column(
        db.String(100),
        nullable=True
    )

    notes = db.Column(db.Text, nullable=True)

    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    parts = db.relationship(
        "PartLine",
        backref="parts_order",
        cascade="all, delete-orphan"
    )


class PartLine(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    parts_order_id = db.Column(
        db.Integer,
        db.ForeignKey("parts_order.id"),
        nullable=False
    )

    part_number = db.Column(
        db.String(100),
        nullable=False
    )

    description = db.Column(
        db.String(250),
        nullable=True
    )

    quantity_ordered = db.Column(
        db.Integer,
        nullable=False,
        default=1
    )

    quantity_received = db.Column(
        db.Integer,
        nullable=False,
        default=0
    )

    notes = db.Column(db.Text, nullable=True)

    @property
    def is_fully_received(self):
        return self.quantity_received >= self.quantity_ordered
