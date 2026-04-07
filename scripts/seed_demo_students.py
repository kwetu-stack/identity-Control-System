import os
import sys
import random
from datetime import datetime, timedelta

from werkzeug.security import generate_password_hash

# Seed scripts should persist changes even if the app defaults to demo mode.
os.environ["DEMO_MODE"] = "false"

# Ensure repo root is on sys.path when running as a script.
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from app import create_app
from core.db import db
from core.qr import generate_qr_token
from core.security import ROLE_GUARD
from models.entry_log import EntryLog
from models.student import Student
from models.user import User


def run():
    app = create_app()
    with app.app_context():
        random.seed(42)

        # ---- Realistic "private university" seed parameters ----
        total_students_target = 800
        inactive_ratio = 0.06
        days_back = 120
        avg_events_per_day = 110  # across all gates/guards
        denied_ratio = 0.06
        # --------------------------------------------------------

        # Ensure we have a few guards for realistic logs.
        guard_usernames = ["guard", "guard.north", "guard.south", "guard.hostels"]
        guard_ids: list[int] = []
        for uname in guard_usernames:
            u = User.query.filter_by(username=uname).first()
            if not u:
                u = User(
                    username=uname,
                    password_hash=generate_password_hash("guard123"),
                    role=ROLE_GUARD,
                    active=True,
                )
                db.session.add(u)
                db.session.flush()
            guard_ids.append(u.id)

        # Create student directory.
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
        programs = ["BBA", "BSc", "BA", "LLB", "BCom", "BEng", "BBIT"]

        created_students = 0
        existing_students = Student.query.count()
        need_to_create = max(0, total_students_target - existing_students)

        start_index = existing_students + 1
        for i in range(start_index, start_index + need_to_create):
            year = random.choice([2021, 2022, 2023, 2024, 2025])
            program = random.choice(programs)
            reg = f"KWT/{program}/{year}/{i:05d}"
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

        # Backfill entry logs so Management dashboard looks "lived in".
        students = Student.query.all()
        active_students = [s for s in students if s.is_active]
        inactive_students = [s for s in students if not s.is_active]

        now = datetime.utcnow()
        created_logs = 0

        for day_offset in range(days_back, -1, -1):
            day = now - timedelta(days=day_offset)
            # Add realistic variation by weekday.
            weekday = day.weekday()  # 0=Mon ... 6=Sun
            weekday_multiplier = 1.15 if weekday in (0, 1, 2, 3) else (0.95 if weekday == 4 else 0.55)

            events_today = int(random.gauss(avg_events_per_day * weekday_multiplier, 18))
            events_today = max(25, min(events_today, 220))

            for _ in range(events_today):
                # Most logs come from active students; a few from inactive for "denied".
                use_inactive = random.random() < 0.03 and len(inactive_students) > 0
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

                # Time-of-day: morning + evening peaks.
                peak_hour = random.choice([7, 8, 9, 16, 17, 18, 19, 20])
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

            # Batch commits for speed.
            if day_offset % 7 == 0:
                db.session.commit()

        db.session.commit()

        print(f"Seeded students: +{created_students} (total now {Student.query.count()})")
        print(f"Seeded entry logs: +{created_logs} (total now {EntryLog.query.count()})")


if __name__ == "__main__":
    run()
