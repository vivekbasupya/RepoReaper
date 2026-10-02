import asyncio

from alembic import context
from reporeaper.config import Settings
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


def run(connection):
    context.configure(connection=connection, target_metadata=None)
    with context.begin_transaction():
        context.run_migrations()


async def main():
    settings = Settings()
    engine = create_async_engine(settings.database_url)
    async with engine.connect() as connection:
        await connection.execute(text("SET lock_timeout = '10s'"))
        await connection.execute(text("SELECT pg_advisory_lock(734910)"))
        await connection.commit()
        await connection.run_sync(run)
        await connection.execute(text("SELECT pg_advisory_unlock(734910)"))
        await connection.commit()
    await engine.dispose()


if context.is_offline_mode():
    raise RuntimeError("Migrations require a real PostgreSQL connection")
asyncio.run(main())
