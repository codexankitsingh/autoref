"""Alembic env.py — connects to our existing database and models."""
from logging.config import fileConfig

from sqlalchemy import pool
from alembic import context

# Import our app's database engine and Base
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from database import engine, Base
# Import ALL models so their metadata is registered on Base
import models  # noqa — triggers models/__init__.py which imports everything

# Alembic Config object
config = context.config

# Set up loggers
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Point Alembic at our metadata for autogenerate
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    from config import get_settings
    settings = get_settings()
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode using our existing engine."""
    connectable = engine

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
