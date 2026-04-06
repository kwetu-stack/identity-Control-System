from werkzeug.security import generate_password_hash

from app import create_app
from core.db import db
from models.user import User
from core.security import ROLE_ADMIN, ROLE_GUARD, ROLE_MANAGEMENT


def create_user(username, password, role):
    existing = User.query.filter_by(username=username).first()
    if existing:
        print(f"{username} already exists.")
        return

    user = User(
        username=username,
        password_hash=generate_password_hash(password),
        role=role,
        active=True,
    )
    db.session.add(user)
    db.session.commit()
    print(f"{username} created successfully.")


def run():
    app = create_app()
    with app.app_context():
        create_user("admin", "admin123", ROLE_ADMIN)
        create_user("guard", "guard123", ROLE_GUARD)
        create_user("manager", "manager123", ROLE_MANAGEMENT)


if __name__ == "__main__":
    run()
