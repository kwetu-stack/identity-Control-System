from datetime import datetime
from core.db import db

class EntryLog(db.Model):
    __tablename__ = "entry_logs"

    id = db.Column(db.Integer, primary_key=True)

    student_id = db.Column(
        db.Integer,
        db.ForeignKey("students.id"),
        nullable=True
    )

    guard_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False
    )

    result = db.Column(db.String(20), nullable=False)  # allowed / denied
    reason = db.Column(db.String(255))

    # 🔒 LOCKED: NAIVE UTC (SQLite-safe)
    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    # ✅ CRITICAL: ORM RELATIONSHIPS (THIS WAS MISSING)
    student = db.relationship("Student", backref="entry_logs")
    guard = db.relationship("User")
