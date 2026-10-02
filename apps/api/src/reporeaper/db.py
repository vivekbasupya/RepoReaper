import json
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from reporeaper.config import Settings


def encode(value: Any) -> str:
    return json.dumps(value, default=str, sort_keys=True, separators=(",", ":"))


class Database:
    def __init__(self, settings: Settings):
        self.engine = create_async_engine(
            settings.database_url,
            pool_size=3,
            max_overflow=0,
            pool_timeout=5,
            connect_args={"timeout": 5, "command_timeout": 10},
        )

    @asynccontextmanager
    async def transaction(self):
        async with self.engine.begin() as connection:
            yield connection

    async def close(self):
        await self.engine.dispose()


async def one(c: AsyncConnection, sql: str, **params) -> dict | None:
    row = (await c.execute(text(sql), params)).mappings().first()
    return dict(row) if row else None


async def many(c: AsyncConnection, sql: str, **params) -> list[dict]:
    return [dict(row) for row in (await c.execute(text(sql), params)).mappings()]


async def command(c: AsyncConnection, run_id: UUID, kind: str, key: str, payload: dict):
    await c.execute(
        text("""
        INSERT INTO outbox(id,run_id,type,dedupe_key,payload)
        VALUES(:id,:run,:kind,:key,CAST(:payload AS jsonb)) ON CONFLICT(dedupe_key) DO NOTHING
    """),
        dict(
            id=uuid4(),
            run=run_id,
            kind=kind,
            key=key,
            payload=encode(
                {
                    "schema_version": 1,
                    "run_id": str(run_id),
                    **payload,
                }
            ),
        ),
    )


async def event(c: AsyncConnection, run_id: UUID, kind: str, payload: dict):
    row = await one(
        c,
        """UPDATE runs SET latest_sequence=latest_sequence+1,version=version+1
        WHERE id=:id RETURNING latest_sequence""",
        id=run_id,
    )
    assert row
    await c.execute(
        text("""INSERT INTO run_events(run_id,sequence,type,payload)
        VALUES(:run,:sequence,:kind,CAST(:payload AS jsonb))"""),
        dict(
            run=run_id,
            sequence=row["latest_sequence"],
            kind=kind,
            payload=encode(payload),
        ),
    )


class LostLease(RuntimeError):
    pass


async def fence(c: AsyncConnection, run_id: UUID, owner: UUID, token: int):
    row = await one(
        c,
        """SELECT id FROM runs WHERE id=:id AND lease_owner=:owner
        AND fence=:token AND lease_until>now() FOR UPDATE""",
        id=run_id,
        owner=owner,
        token=token,
    )
    if not row:
        raise LostLease("Stale graph owner cannot commit")
