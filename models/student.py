from core.db import db


class Student(db.Model):
    __tablename__ = "students"

    id = db.Column(db.Integer, primary_key=True)

    # Core identity
    registration_number = db.Column(db.String(50), unique=True, nullable=False)
    full_name = db.Column(db.String(120), nullable=False)

    # QR identity (Phase 2 – assisted verification)
    qr_token = db.Column(db.String(64), unique=True, nullable=True)

    # Status control
    is_active = db.Column(db.Boolean, default=True)

    # Optional (future-proofing)
    photo_path = db.Column(db.String(255), nullable=True)

    # Audit
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    def __repr__(self):
        return f"<Student {self.registration_number} - {self.full_name}>"
