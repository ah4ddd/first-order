import sys
from os.path import dirname, abspath

sys.path.insert(0, dirname(dirname(dirname(abspath(__file__)))))

import asyncio
from logging.config import fileConfig
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config # Use the async variant!
from alembic import context

# 1. FIX: Absolute imports instead of relative dots.
# Make sure your project root is in your PYTHONPATH when running alembic.
from app.db_models import Base # type: ignore
from app.config import get_settings # type: ignore

# This is the Alembic Config object
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Provide target metadata for autogenerate support
target_metadata = Base.metadata

# Overwrite the alembic.ini file's sqlalchemy.url with your dynamic environment configuration
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    # Strip the async prefix just in case for generating offline raw SQL scripts
    url = settings.database_url.replace("+asyncpg", "")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    """Helper runner that actually executes inside the transaction block."""
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations in 'online' mode using an Async Engine."""

    # Create the modern configuration dictionary explicitly setting up the driver
    configuration = config.get_section(config.config_ini_section, {})

    # Build a true modern Async Engine from config
    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    # Use the async connection pipeline to run sync migration operations safely
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    # Run the async online function using the event loop execution wrapper
    asyncio.run(run_migrations_online())
