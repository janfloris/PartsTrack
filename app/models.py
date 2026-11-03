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

    def __repr__(self):
        return f"<WorkItem {self.number}>"