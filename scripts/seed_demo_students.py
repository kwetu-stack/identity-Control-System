import os
import sys

# Seed scripts should persist changes even if the app defaults to demo mode.
os.environ["DEMO_MODE"] = "false"

# Ensure repo root is on sys.path when running as a script.
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from app import create_app
from core.seed import seed_demo_data
from models.student import Student


def run():
    app = create_app()
    with app.app_context():
        created_students, created_logs = seed_demo_data()
        print(f"Seeded students: +{created_students} (total now {Student.query.count()})")
        print(f"Seeded entry logs: +{created_logs}")


if __name__ == "__main__":
    run()
