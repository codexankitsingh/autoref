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
    """Initialize database using Alembic migrations.
    
    On startup, runs any pending Alembic migrations. This ensures:
    - Local SQLite and production PostgreSQL both get new tables/columns
    - Existing data is preserved (unlike create_all which can't add columns)
    - Schema changes are versioned and reversible
    """
    from models import user, mail_account, job_application, recipient, email_thread, message, follow_up_job, reply, scraped_job  # noqa
    from sqlalchemy import inspect

    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()

    # One-time legacy migration: if old schema exists (users table without password_hash),
    # drop everything and recreate with the new auth schema.
    if "users" in existing_tables:
        columns = [col["name"] for col in inspector.get_columns("users")]
        if "password_hash" not in columns:
            print("⚠️  Old schema detected (no auth columns). Resetting database for v1.0...")
            Base.metadata.drop_all(bind=engine)
            print("🗑️  Old tables dropped.")

    # Use Alembic to run any pending migrations
    try:
        from alembic.config import Config
        from alembic import command
        import os

        # Always ensure base tables exist first
        Base.metadata.create_all(bind=engine)

        alembic_ini = os.path.join(os.path.dirname(__file__), "alembic.ini")
        if os.path.exists(alembic_ini):
            alembic_cfg = Config(alembic_ini)
            
            # Since our migration is idempotent, we always run upgrade.
            # This handles both fresh DBs and old DBs properly.
            command.upgrade(alembic_cfg, "head")
            print("✅ Alembic migrations applied")
            
            # ── Fallback Patch for existing bugged deployments ──
            # If the DB was incorrectly stamped as head without adding columns, 
            # we manually patch it here.
            with engine.connect() as conn:
                from sqlalchemy import text
                inspector = inspect(engine)
                msg_columns = [col["name"] for col in inspector.get_columns("messages")]
                if "tracking_id" not in msg_columns:
                    conn.execute(text("ALTER TABLE messages ADD COLUMN tracking_id VARCHAR(64)"))
                    conn.execute(text("ALTER TABLE messages ADD COLUMN open_count INTEGER DEFAULT 0"))
                    conn.execute(text("ALTER TABLE messages ADD COLUMN opened_at TIMESTAMP"))
                    conn.execute(text("ALTER TABLE messages ADD COLUMN last_opened_at TIMESTAMP"))
                    conn.commit()
                    print("🔧 Manually patched missing tracking columns in messages table.")
        else:
            print("✅ Database initialized (no alembic.ini found)")
    except Exception as e:
        print(f"⚠️  Alembic migration failed: {e}. Falling back to create_all...")
        Base.metadata.create_all(bind=engine)

