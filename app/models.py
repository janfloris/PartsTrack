
from datetime import datetime, timezone

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from app import db


class WorkItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    number = db.Column(db.String(50), nullable=False)
    type = db.Column(db.String(50), nullable=False)
    customer = db.Column(db.String(150), nullable=False)
    technician = db.Column(db.String(100), nullable=True)
    notes = db.Column(db.Text, nullable=True)

    appointment_date = db.Column(
        db.Date,
        nullable=True
    )

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


class Technician(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)

    def __repr__(self):
        return f"<Technician {self.name}>"


class Supplier(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), unique=True, nullable=False)

    def __repr__(self):
        return f"<Supplier {self.name}>"


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)

    username = db.Column(
        db.String(80),
        unique=True,
        nullable=False
    )

    password_hash = db.Column(
        db.String(256),
        nullable=False
    )

    role = db.Column(
        db.String(20),
        nullable=False,
        default="employee"
    )

    is_active = db.Column(
        db.Boolean,
        nullable=False,
        default=True
    )

    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self):
        return self.role == "admin"

    def __repr__(self):
        return f"<User {self.username}>"

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False
    )

    work_item_id = db.Column(
        db.Integer,
        db.ForeignKey("work_item.id"),
        nullable=False
    )

    message = db.Column(
        db.String(500),
        nullable=False
    )

    is_read = db.Column(
        db.Boolean,
        default=False,
        nullable=False
    )

    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    user = db.relationship(
        "User",
        backref="notifications"
    )

    work_item = db.relationship(
        "WorkItem",
        backref="notifications"
    )

    def __repr__(self):
        return f"<Notification {self.id}>"
    