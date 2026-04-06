from flask import current_app, has_app_context
from flask_sqlalchemy import SQLAlchemy
from flask_sqlalchemy.session import Session


class DemoSession(Session):
    def commit(self):
        if has_app_context() and current_app.config.get("DEMO_MODE", False):
            self.rollback()
            return
        return super().commit()


db = SQLAlchemy(session_options={"class_": DemoSession})
