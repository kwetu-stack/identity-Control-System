import os
from dotenv import load_dotenv

load_dotenv()


class BaseConfig:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key")

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

    SQLALCHEMY_DATABASE_URI = (
        os.environ.get("DATABASE_URL")
        or "sqlite:///" + os.path.join(os.getcwd(), "identity_control.db")
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False


class DevelopmentConfig(BaseConfig):
    ENV = "development"
    DEBUG = False



class ProductionConfig(BaseConfig):
    ENV = "production"
    DEBUG = False

# Entry control rules
MIN_REENTRY_MINUTES = 10
