"""Alembic migration environment configuration."""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from src.core.config import get_settings
from src.models.db.api_key import ApiKey  # noqa: F401

# Import all models to ensure they are registered with Base.metadata
from src.models.db.base import Base
from src.models.db.consent import Consent  # noqa: F401
from src.models.db.conversation import Conversation, ConversationMessage  # noqa: F401
from src.models.db.event import AnalyticsEvent  # noqa: F401
from src.models.db.experiment import (  # noqa: F401
    Experiment,
    ExperimentAssignment,
    ExperimentMetric,
)
from src.models.db.organization import Organization  # noqa: F401
from src.models.db.session import Session  # noqa: F401
from src.models.db.session_chunk import SessionChunk  # noqa: F401
from src.models.db.transcript import Transcript  # noqa: F401
from src.models.db.user import User  # noqa: F401

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Get database URL from settings (bypass configparser to avoid % interpolation issues)
settings = get_settings()
database_url = str(settings.database_url)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.
    """
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run migrations with the provided connection."""
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode with async engine."""
    connectable = create_async_engine(database_url, poolclass=pool.NullPool)

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.
    """
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
