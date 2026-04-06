from core.db import db
from models.student import Student
from core.qr import generate_qr_token


def run():
    students = Student.query.filter(Student.qr_token.is_(None)).all()
    count = 0

    for student in students:
        student.qr_token = generate_qr_token()
        count += 1

    if count:
        db.session.commit()

    print(f"Assigned QR tokens to {count} students.")


if __name__ == "__main__":
    run()
