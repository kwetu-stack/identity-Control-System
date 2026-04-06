# Role constants
ROLE_ADMIN = "admin"
ROLE_GUARD = "guard"
ROLE_MANAGEMENT = "management"


ALL_ROLES = {ROLE_ADMIN, ROLE_GUARD, ROLE_MANAGEMENT}
from functools import wraps
from flask import abort, current_app, has_app_context
from flask_login import current_user, login_required


def role_required(required_role):
    """
    Enforces that the current user has a specific role.
    """

    def decorator(fn):
        @wraps(fn)
        @login_required
        def wrapper(*args, **kwargs):
            if has_app_context() and current_app.config.get("DEMO_MODE", False):
                return fn(*args, **kwargs)

            if not hasattr(current_user, "role"):
                abort(403)

            if current_user.role != required_role:
                abort(403)

            return fn(*args, **kwargs)

        return wrapper

    return decorator
