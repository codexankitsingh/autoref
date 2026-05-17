from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from config import get_settings

settings = get_settings()

# SQLite needs check_same_thread=False for FastAPI
connect_args = {}
if settings.database_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """Dependency for FastAPI endpoints."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables. Auto-resets if schema is outdated (one-time migration)."""
    from models import user, mail_account, job_application, recipient, email_thread, message, follow_up_job, reply  # noqa
    from sqlalchemy import inspect

    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()

    # One-time migration: if old schema exists (users table without password_hash),
    # drop everything and recreate with the new auth schema.
    if "users" in existing_tables:
        columns = [col["name"] for col in inspector.get_columns("users")]
        if "password_hash" not in columns:
            print("⚠️  Old schema detected (no auth columns). Resetting database for v1.0...")
            Base.metadata.drop_all(bind=engine)
            print("🗑️  Old tables dropped.")

    Base.metadata.create_all(bind=engine)

