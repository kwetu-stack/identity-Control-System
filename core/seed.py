import os
import random
from datetime import datetime, timedelta

from werkzeug.security import generate_password_hash

from core.db import db
from core.qr import generate_qr_token
from core.security import ROLE_ADMIN, ROLE_GUARD, ROLE_MANAGEMENT
from models.entry_log import EntryLog
from models.student import Student
from models.user import User


def ensure_user(username: str, password: str, role: str) -> User:
    user = User.query.filter_by(username=username).first()
    if user:
        return user

    user = User(
        username=username,
        password_hash=generate_password_hash(password),
        role=role,
        active=True,
    )
    db.session.add(user)
    db.session.flush()
    return user


def seed_demo_data(
    total_students_target: int = 780,
    inactive_ratio: float = 0.08,
    days_back: int = 35,
    avg_events_per_day: int = 115,
    denied_ratio: float = 0.06,
) -> tuple[int, int]:
    """Seed the database with demo users, students, and entry logs.

    This is intended for fresh deployments when the database is empty.
    """
    existing_students = Student.query.count()
    if existing_students > 0:
        return 0, 0

    guard_usernames = [
        "guard.north",
        "guard.south",
        "guard.east",
        "guard.west",
        "guard.hostels",
    ]

    ensure_user("admin", "admin123", ROLE_ADMIN)
    ensure_user("manager", "manager123", ROLE_MANAGEMENT)
    guard_ids: list[int] = []
    for uname in guard_usernames:
        guard = ensure_user(uname, "guard123", ROLE_GUARD)
        guard_ids.append(guard.id)

    first_names = [
        "Amina", "Brian", "Cynthia", "David", "Esther", "Farid", "Grace", "Hassan",
        "Ivy", "James", "Kevin", "Lilian", "Moses", "Naomi", "Oscar", "Patricia",
        "Quentin", "Ruth", "Samuel", "Tanya", "Umar", "Valerie", "Wycliffe", "Xavier",
        "Yvonne", "Zachary",
    ]
    last_names = [
        "Mwangi", "Otieno", "Njoroge", "Wambui", "Kiptoo", "Mutiso", "Ochieng",
        "Kamau", "Wanjiku", "Chebet", "Maina", "Kariuki", "Mumo", "Wekesa",
        "Naliaka", "Kibet", "Wanyama", "Korir", "Achieng", "Muthoni",
    ]
    programs = [
        ("Bachelor of Business Administration", "BBA"),
        ("Bachelor of Science in Computer Science", "BSCS"),
        ("Bachelor of Commerce", "BCOM"),
        ("Bachelor of Laws", "LLB"),
        ("Bachelor of Science", "BSc"),
        ("Bachelor of Engineering", "BEng"),
        ("Bachelor of Science in Information Technology", "BSIT"),
    ]

    random.seed(42)
    created_students = 0
    start_index = 1

    for student_index in range(start_index, start_index + total_students_target):
        admit_year = random.choice([2022, 2023, 2024, 2025])
        _, program_code = random.choice(programs)
        reg = f"KWU/{program_code}/{str(admit_year)[-2:]}/{student_index:05d}"
        if Student.query.filter_by(registration_number=reg).first():
            continue

        full_name = f"{random.choice(first_names)} {random.choice(last_names)}"
        is_active = random.random() > inactive_ratio

        db.session.add(
            Student(
                registration_number=reg,
                full_name=full_name,
                is_active=is_active,
                qr_token=generate_qr_token(),
            )
        )
        created_students += 1

    db.session.commit()

    students = Student.query.all()
    active_students = [s for s in students if s.is_active]
    inactive_students = [s for s in students if not s.is_active]

    now = datetime.utcnow()
    created_logs = 0

    for day_offset in range(days_back, -1, -1):
        day = now - timedelta(days=day_offset)
        weekday = day.weekday()
        weekday_multiplier = 1.2 if weekday in (0, 1, 2, 3) else (0.9 if weekday == 4 else 0.45)
        events_today = int(random.gauss(avg_events_per_day * weekday_multiplier, 18))
        events_today = max(25, min(events_today, 220))

        for _ in range(events_today):
            use_inactive = random.random() < 0.03 and inactive_students
            student = random.choice(inactive_students if use_inactive else active_students)
            guard_id = random.choice(guard_ids)

            denied = (not student.is_active) or (random.random() < denied_ratio)
            if denied:
                result = "denied"
                reason = random.choice([
                    "Re-entry too soon",
                    "Student inactive",
                    "Invalid QR",
                    "Manual verification failed",
                ])
            else:
                result = "allowed"
                reason = random.choice([
                    "Verified manually",
                    "Verified via QR",
                ])

            peak_hour = random.choice([7, 8, 9, 12, 13, 16, 17, 18, 19])
            minute = random.randint(0, 59)
            second = random.randint(0, 59)
            created_at = day.replace(hour=peak_hour, minute=minute, second=second, microsecond=0)

            db.session.add(
                EntryLog(
                    student_id=student.id,
                    guard_id=guard_id,
                    result=result,
                    reason=reason,
                    created_at=created_at,
                )
            )
            created_logs += 1

        if day_offset % 7 == 0:
            db.session.commit()

    db.session.commit()
    return created_students, created_logs
