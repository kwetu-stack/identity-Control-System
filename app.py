import os
from flask import Flask, Response, flash, redirect, render_template, request, session, url_for
from flask_login import (
    LoginManager, login_required, login_user, logout_user, current_user
)
import csv
from io import StringIO
from config.settings import DevelopmentConfig, ProductionConfig
from models.user import User
from core.security import ALL_ROLES, ROLE_ADMIN, ROLE_GUARD, ROLE_MANAGEMENT
from werkzeug.security import check_password_hash
from core.db import db
from core.security import role_required
from models.student import Student
from models.entry_log import EntryLog
from core.seed import seed_demo_data
from datetime import datetime, timedelta, timezone, date
from config.settings import MIN_REENTRY_MINUTES
from sqlalchemy import or_


DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() == "true"


def is_demo():
    return DEMO_MODE


def get_config_class():
    app_env = (
        os.getenv("APP_ENV")
        or os.getenv("FLASK_ENV")
        or ("production" if os.getenv("RAILWAY_ENVIRONMENT_NAME") else "development")
    ).lower()
    if app_env == "production":
        return ProductionConfig
    return DevelopmentConfig


def describe_database_backend(uri: str) -> str:
    if not uri:
        return "unknown"
    lowered = uri.lower()
    if lowered.startswith("sqlite:"):
        return "sqlite"
    if lowered.startswith("postgresql:"):
        return "postgresql"
    if lowered.startswith("mysql:"):
        return "mysql"
    return lowered.split(":", 1)[0]


login_manager = LoginManager()
login_manager.login_view = "login"


def get_demo_user():
    demo_role = session.get("demo_role", ROLE_ADMIN)
    if demo_role not in ALL_ROLES:
        demo_role = ROLE_ADMIN

    demo_user = User.query.order_by(User.id.asc()).first()
    if demo_user:
        # In demo mode we allow "view as role" without persisting it.
        demo_user.role = demo_role
        return demo_user

    return User(
        id=1,
        username="demo",
        password_hash="",
        role=demo_role,
        active=True
    )


def create_app():
    app = Flask(__name__)
    app.config.from_object(get_config_class())
    app.config["DEMO_MODE"] = DEMO_MODE
    app.jinja_env.globals["is_demo"] = is_demo

    # DB init
    db.init_app(app)
    with app.app_context():
        db_uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
        app.logger.info(
            "Starting app with DEMO_MODE=%s, ENV=%s, database_backend=%s",
            DEMO_MODE,
            app.config.get("ENV"),
            describe_database_backend(db_uri),
        )
        db.create_all()
        from werkzeug.security import generate_password_hash

        # ---- DEV USER SEED (SAFE TO REMOVE LATER) ----
        if not User.query.first():
            admin = User(
                username="admin",
                password_hash=generate_password_hash("admin123"),
                role=ROLE_ADMIN
            )
            guard = User(
                username="guard",
                password_hash=generate_password_hash("guard123"),
                role=ROLE_GUARD
            )
            manager = User(
                username="manager",
                password_hash=generate_password_hash("manager123"),
                role=ROLE_MANAGEMENT
            )

            db.session.add_all([admin, guard, manager])
            db.session.commit()
        # --------------------------------------------

        if not is_demo():
            created_students, created_logs = seed_demo_data()
            if created_students or created_logs:
                app.logger.info(
                    f"Seeded empty deployment database with {created_students} students and {created_logs} logs."
                )
            else:
                app.logger.info(
                    "Seed skipped because students already exist in the configured database."
                )
        else:
            app.logger.info("Demo mode is enabled; persistent startup seed is disabled.")

    # Login manager
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        user = db.session.get(User, int(user_id))
        if user is None and is_demo() and int(user_id) == 1:
            return get_demo_user()
        return user

    @app.before_request
    def enable_demo_mode_access():
        if not is_demo() or request.endpoint == "static":
            return None

        if not current_user.is_authenticated:
            login_user(get_demo_user())
        else:
            # Keep demo role changes reflected for the current request.
            current_user.role = session.get("demo_role", getattr(current_user, "role", ROLE_ADMIN))

        route_hint = f"{request.endpoint or ''} {request.path}".lower()
        if "delete" in route_hint or "remove" in route_hint:
            flash("Demo Mode: Delete disabled.", "warning")
            return redirect(request.referrer or url_for("post_login"))

        if request.method == "GET" and request.endpoint == "assign_qr_tokens":
            flash("Demo Mode: Action simulated successfully.", "info")
            return redirect(request.referrer or url_for("post_login"))

        if request.method == "POST":
            flash("Demo Mode: Action simulated successfully.", "info")
            return redirect(request.referrer or url_for("post_login"))

        return None

    @app.route("/demo/switch-role/<role>")
    @login_required
    def demo_switch_role(role: str):
        """
        Demo-only helper: switch the current demo user's "view as" role.
        This does not modify the DB; it only stores role in the session.
        """
        if not is_demo():
            return redirect(url_for("post_login"))

        role = (role or "").strip().lower()
        if role not in ALL_ROLES:
            flash("Unknown role.", "warning")
            return redirect(request.referrer or url_for("post_login"))

        session["demo_role"] = role
        login_user(get_demo_user())
        flash(f"Demo Mode: viewing as {role}.", "info")
        return redirect(url_for("post_login"))

    def process_verification_result(student, result, reason):
        """Helper function to log and return verification result."""
        db.session.add(
            EntryLog(
                student_id=student.id if student else None,
                guard_id=current_user.id,
                result=result,
                reason=reason
            )
        )
        db.session.commit()
        return render_template(
            "guard/verify_student.html",
            student=student,
            message=f"Entry {result}. Reason: {reason}",
            last_entry=None
        )

    def process_student_verification(student):
        """Helper function to handle student verification logic."""
        # Time-based re-entry lock (timezone-aware UTC)
        last_entry = (
            EntryLog.query
            .filter_by(student_id=student.id, result="allowed")
            .order_by(EntryLog.created_at.desc())
            .first()
        )

        if last_entry:
            # Ensure last_entry.created_at is treated as UTC
            last_entry_time = last_entry.created_at.replace(tzinfo=timezone.utc) if last_entry.created_at.tzinfo is None else last_entry.created_at
            now = datetime.now(timezone.utc)
            delta = now - last_entry_time

            if delta < timedelta(minutes=MIN_REENTRY_MINUTES):
                remaining = MIN_REENTRY_MINUTES - int(delta.total_seconds() // 60)

                message = (
                    f"Entry denied. Last entry was "
                    f"{int(delta.total_seconds() // 60)} minute(s) ago. "
                    f"Try again in {remaining} minute(s)."
                )

                db.session.add(
                    EntryLog(
                        student_id=student.id,
                        guard_id=current_user.id,
                        result="denied",
                        reason="Re-entry too soon"
                    )
                )
                db.session.commit()

                return render_template(
                    "guard/verify_student.html",
                    student=student,
                    message=message,
                    last_entry=last_entry
                )

        # ✅ ALLOWED ENTRY
        db.session.add(
            EntryLog(
                student_id=student.id,
                guard_id=current_user.id,
                result="allowed",
                reason="Verified manually"
            )
        )
        db.session.commit()

        # Refresh last entry AFTER commit
        last_entry = (
            EntryLog.query
            .filter_by(student_id=student.id, result="allowed")
            .order_by(EntryLog.created_at.desc())
            .first()
        )

        return render_template(
            "guard/verify_student.html",
            student=student,
            message="Student verified.",
            last_entry=last_entry
        )

    @app.route("/")
    @login_required
    def index():
        return redirect(url_for("post_login"))

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if is_demo():
            if not current_user.is_authenticated:
                login_user(get_demo_user())
            return redirect(url_for("post_login"))

        error = None

        if request.method == "POST":
            username = request.form.get("username")
            password = request.form.get("password")

            user = User.query.filter_by(username=username).first()

            if not user:
                error = "Invalid credentials"
            elif not check_password_hash(user.password_hash, password):
                error = "Invalid credentials"
            else:
                login_user(user)
                return redirect(url_for("post_login"))

        return render_template("auth/login.html", error=error)

    @app.route("/post-login")
    @login_required
    def post_login():
        if current_user.role == ROLE_ADMIN:
            return redirect("/admin")
        if current_user.role == ROLE_GUARD:
            return redirect("/guard")
        if current_user.role == ROLE_MANAGEMENT:
            return redirect("/management")

        return redirect(url_for("logout"))

    @app.route("/admin")
    @login_required
    @role_required(ROLE_ADMIN)
    def admin_dashboard():
        return render_template("admin/dashboard.html")

    @app.route("/guard")
    @login_required
    @role_required(ROLE_GUARD)
    def guard_dashboard():
        logs = (
            EntryLog.query
            .order_by(EntryLog.created_at.desc())
            .limit(12)
            .all()
        )
        return render_template("guard/dashboard.html", logs=logs)

    @app.route("/guard/verify", methods=["GET", "POST"])
    @login_required
    @role_required(ROLE_GUARD)
    def guard_verify_student():
        student = None
        message = None
        last_entry = None

        if request.method == "POST":
            reg_no = request.form.get("registration_number")

            # ❌ No registration number
            if not reg_no:
                return process_verification_result(
                    student=None,
                    result="denied",
                    reason="No registration number entered"
                )

            else:
                student = Student.query.filter_by(
                    registration_number=reg_no
                ).first()

                # ❌ Student not found
                if not student:
                    return process_verification_result(
                        student=None,
                        result="denied",
                        reason="Student not found"
                    )

                # ❌ Student inactive
                elif not student.is_active:
                    return process_verification_result(
                        student=student,
                        result="denied",
                        reason="Student inactive"
                    )

                else:
                    # Reuse EXACT Phase 1 verification logic
                    return process_student_verification(student)

        return render_template(
            "guard/verify_student.html",
            student=student,
            message=message,
            last_entry=last_entry
        )

    @app.route("/guard/verify-qr", methods=["POST"])
    @login_required
    @role_required(ROLE_GUARD)
    def verify_qr():
        qr_token = request.form.get("qr_token", "").strip()

        if not qr_token:
            return process_verification_result(
                student=None,
                result="denied",
                reason="empty_qr"
            )

        student = Student.query.filter_by(qr_token=qr_token).first()

        if not student:
            return process_verification_result(
                student=None,
                result="denied",
                reason="invalid_qr"
            )

        # Reuse EXACT Phase 1 verification logic
        return process_student_verification(student)

    @app.route("/management")
    @login_required
    @role_required(ROLE_MANAGEMENT)
    def management_dashboard():
        # Use UTC date range for accurate filtering
        now = datetime.now(timezone.utc)
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = start_of_day + timedelta(days=1)

        total_students = Student.query.count()

        entries_today = (
            EntryLog.query
            .filter(EntryLog.created_at >= start_of_day, EntryLog.created_at < end_of_day)
            .count()
        )

        allowed_today = (
            EntryLog.query
            .filter(
                EntryLog.created_at >= start_of_day,
                EntryLog.created_at < end_of_day,
                EntryLog.result == "allowed"
            )
            .count()
        )

        denied_today = (
            EntryLog.query
            .filter(
                EntryLog.created_at >= start_of_day,
                EntryLog.created_at < end_of_day,
                EntryLog.result == "denied"
            )
            .count()
        )

        return render_template(
            "management/dashboard.html",
            total_students=total_students,
            entries_today=entries_today,
            allowed_today=allowed_today,
            denied_today=denied_today
        )

    @app.route("/management/entry-logs/export")
    @login_required
    @role_required(ROLE_MANAGEMENT)
    def export_entry_logs_csv():
        logs = (
            EntryLog.query
            .order_by(EntryLog.created_at.desc())
            .all()
        )

        si = StringIO()
        writer = csv.writer(si)

        # Header
        writer.writerow([
            "Date (UTC)",
            "Student Name",
            "Registration Number",
            "Result",
            "Reason",
            "Guard ID"
        ])

        # Rows
        for log in logs:
            # Ensure created_at is treated as UTC for strftime
            utc_time = log.created_at.replace(tzinfo=timezone.utc) if log.created_at.tzinfo is None else log.created_at
            writer.writerow([
                utc_time.strftime("%Y-%m-%d %H:%M:%S"),
                log.student.full_name if log.student else "",
                log.student.registration_number if log.student else "",
                log.result,
                log.reason,
                log.guard_id
            ])

        output = si.getvalue()
        si.close()

        return Response(
            output,
            mimetype="text/csv",
            headers={
                "Content-Disposition": "attachment; filename=entry_logs.csv"
            }
        )

    @app.route("/management/entry-logs")
    @login_required
    @role_required(ROLE_MANAGEMENT)
    def management_entry_logs():
        logs = (
            EntryLog.query
            .order_by(EntryLog.created_at.desc())
            .limit(200)
            .all()
        )

        return render_template(
            "management/entry_logs.html",
            logs=logs
        )

    @app.route("/admin/students")
    @login_required
    @role_required(ROLE_ADMIN)
    def list_students():
        q = (request.args.get("q") or "").strip()
        query = Student.query
        if q:
            like = f"%{q}%"
            query = query.filter(
                or_(
                    Student.full_name.ilike(like),
                    Student.registration_number.ilike(like),
                )
            )
        students = query.order_by(Student.full_name.asc()).limit(300).all()
        return render_template(
            "admin/list_students.html",
            students=students
        )

    @app.route("/admin/students/add", methods=["GET", "POST"])
    @login_required
    @role_required(ROLE_ADMIN)
    def add_student():
        error = None
        success = None

        if request.method == "POST":
            reg_no = request.form.get("registration_number")
            full_name = request.form.get("full_name")

            if not reg_no or not full_name:
                error = "All fields are required."
            else:
                existing = Student.query.filter_by(
                    registration_number=reg_no
                ).first()

                if existing:
                    error = "Student with this registration number already exists."
                else:
                    student = Student(
                        registration_number=reg_no,
                        full_name=full_name,
                        is_active=True
                    )
                    db.session.add(student)
                    db.session.commit()
                    success = "Student added successfully."

        return render_template(
            "admin/add_student.html",
            error=error,
            success=success
        )
        
    @app.route("/management/students/<int:student_id>/entries")
    @login_required
    @role_required(ROLE_MANAGEMENT)
    def management_student_entries(student_id):
        student = Student.query.get_or_404(student_id)

        logs = (
            EntryLog.query
            .filter_by(student_id=student.id)
            .order_by(EntryLog.created_at.desc())
            .all()
        )

        return render_template(
            "management/student_entry_history.html",
            student=student,
            logs=logs
        )
    
  

    @app.route("/logout")
    @login_required
    def logout():
        if is_demo():
            flash("Demo Mode remains active.", "info")
            return redirect(url_for("post_login"))

        logout_user()
        return redirect(url_for("login"))

    @app.route("/admin/assign-qr-tokens")
    @login_required
    @role_required(ROLE_ADMIN)
    def assign_qr_tokens():
        from core.qr import generate_qr_token

        students = Student.query.filter(Student.qr_token.is_(None)).all()

        for s in students:
            s.qr_token = generate_qr_token()

        db.session.commit()

        return redirect(url_for("admin_dashboard"))

    @app.route("/healthz")
    def healthz():
        return Response("ok", mimetype="text/plain")

    return app

app = create_app()

if __name__ == "__main__":
    app.run()
