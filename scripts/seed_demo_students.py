from app import create_app
from core.db import db
from core.qr import generate_qr_token
from models.student import Student


def run():
    app = create_app()
    with app.app_context():

        demo_students = [
            ("DEMO001", "Alice Demo", True),
            ("DEMO002", "Bob Demo", True),
            ("DEMO003", "Carol Demo", True),
            ("DEMO004", "Dave Demo", False),
            ("DEMO005", "Eve Demo", False),
        ]

        created = 0

        for reg, name, active in demo_students:
            if not Student.query.filter_by(registration_number=reg).first():
                db.session.add(
                    Student(
                        registration_number=reg,
                        full_name=name,
                        is_active=active,
                        qr_token=generate_qr_token(),
                    )
                )
                created += 1

        db.session.commit()
        print(f"Demo students seeded: {created}")


if __name__ == "__main__":
    run()
