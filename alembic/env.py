import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine

from alembic import context

from app.core.config import get_settings
from app.core.database import Base
import app.models.base  # noqa: F401

settings = get_settings()
config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True, dialect_opts={"paramstyle": "named"})

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = context.config.attributes.get("connection", None)

    if connectable is None:
        connectable = AsyncEngine(Base.metadata.bind) if isinstance(Base.metadata.bind, AsyncEngine) else Base.metadata.bind

    if isinstance(connectable, AsyncEngine):
        async def async_run() -> None:
            async with connectable.connect() as connection:
                await connection.run_sync(do_run_migrations)

        asyncio.run(async_run())
    else:
        with connectable.connect() as connection:
            do_run_migrations(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
