import os
from dotenv import load_dotenv

load_dotenv()


def resolve_database_url() -> str:
    database_url = (
        os.environ.get("DATABASE_URL")
        or os.environ.get("DATABASE_PRIVATE_URL")
        or os.environ.get("DATABASE_PUBLIC_URL")
        or os.environ.get("POSTGRES_URL")
        or os.environ.get("POSTGRESQL_URL")
    )
    if database_url:
        # SQLAlchemy expects postgresql://, while some hosts still expose postgres://
        if database_url.startswith("postgres://"):
            return database_url.replace("postgres://", "postgresql://", 1)
        return database_url

    return "sqlite:///" + os.path.join(os.getcwd(), "identity_control.db")


class BaseConfig:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key")

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

    SQLALCHEMY_DATABASE_URI = (
        resolve_database_url()
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
