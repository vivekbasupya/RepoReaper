"""PostgreSQL-driven leader and recovery loop. Redis delivery is only a hint."""

import asyncio
from uuid import UUID, uuid4

import anyio
import httpx
from sqlalchemy import text

from reporeaper.adapters import HttpSandbox
from reporeaper.config import Settings
from reporeaper.db import Database, command, encode, event, many, one
from reporeaper.domain import ExecutionRequest
from reporeaper.faults import crash_once
from reporeaper.worker import celery


async def tick(db: Database, sandbox: HttpSandbox, owner: UUID):
    async with db.transaction() as c:
        leader = await one(
            c,
            """INSERT INTO service_leases VALUES('dispatcher',:owner,now()+interval '20 seconds')
            ON CONFLICT(name) DO UPDATE SET owner=:owner,lease_until=excluded.lease_until
            WHERE service_leases.lease_until<now() OR service_leases.owner=:owner RETURNING owner""",
            owner=owner,
        )
        if not leader:
            return
        # Expired graph claims are eligible for the SAME command; do not create a new run.
        commands = await many(
            c,
            """SELECT o.* FROM outbox o LEFT JOIN command_receipts r ON r.command_id=o.id
            WHERE o.completed_at IS NULL AND o.error IS NULL
            AND (o.published_at IS NULL OR o.published_at<now()-interval '5 seconds')
            AND (r.command_id IS NULL OR r.lease_until<now()) ORDER BY o.created_at LIMIT 20""",
        )
        pending = await many(
            c,
            """SELECT i.*,r.cancel_requested,r.status AS run_status,r.pending_intent FROM execution_intents i
            JOIN runs r ON r.id=i.run_id WHERE NOT i.consumed AND i.dispatchable""",
        )
        cancelled = await many(
            c, "SELECT id FROM runs WHERE cancel_requested AND status='cancelling'"
        )
    for cmd in commands:
        if cmd["type"] == "graph":
            # Celery publish is unavoidable blocking I/O, explicitly bounded.
            await anyio.to_thread.run_sync(
                lambda command_id=str(cmd["id"]): celery.send_task(
                    "reporeaper.segment", args=[command_id], queue="graph"
                ),
                limiter=anyio.CapacityLimiter(1),
            )
        elif cmd["type"] == "execute":
            async with db.transaction() as c:
                intent = await one(
                    c,
                    "SELECT i.*,r.cancel_requested FROM execution_intents i JOIN runs r ON r.id=i.run_id WHERE i.id=:id",
                    id=UUID(cmd["payload"]["execution_id"]),
                )
            if not intent or not intent["dispatchable"] or not intent["required_checkpoint_id"]:
                continue
            if not intent["cancel_requested"]:
                await sandbox.submit(ExecutionRequest.model_validate(intent["request"]))
                await crash_once(db, intent["run_id"], "after_submission")
            async with db.transaction() as c:
                await c.execute(
                    text("UPDATE outbox SET completed_at=now() WHERE id=:id"), {"id": cmd["id"]}
                )
        else:
            async with db.transaction() as c:
                await c.execute(
                    text("UPDATE outbox SET error='Unsupported durable command type' WHERE id=:id"),
                    {"id": cmd["id"]},
                )
            continue
        async with db.transaction() as c:
            await c.execute(
                text("UPDATE outbox SET published_at=now(),attempts=attempts+1 WHERE id=:id"),
                {"id": cmd["id"]},
            )
    for intent in pending:
        try:
            if intent["cancel_requested"]:
                result = await sandbox.cancel(intent["id"])
            else:
                result = await sandbox.status(intent["id"])
        except httpx.HTTPStatusError as error:
            if error.response.status_code != 404:
                raise
            # Uncertain remote submission: resubmit the same ID/hash, never a new attempt.
            if not intent["cancel_requested"]:
                await sandbox.submit(ExecutionRequest.model_validate(intent["request"]))
            continue
        if result.status not in {"completed", "environment_failure", "timed_out", "cancelled"}:
            continue
        async with db.transaction() as c:
            run = await one(c, "SELECT * FROM runs WHERE id=:id FOR UPDATE", id=intent["run_id"])
            await c.execute(
                text(
                    "UPDATE execution_intents SET result=CAST(:result AS jsonb) WHERE id=:id AND result IS NULL"
                ),
                dict(id=intent["id"], result=encode(result.model_dump(mode="json"))),
            )
            if not run["cancel_requested"] and run["pending_intent"] == intent["id"]:
                await command(
                    c,
                    run["id"],
                    "graph",
                    f"resume/{intent['id']}/{result.result_version}",
                    {
                        "execution_id": str(intent["id"]),
                        "checkpoint_id": intent["required_checkpoint_id"],
                        "graph_version": "1",
                    },
                )
            if run["cancel_requested"] and result.cleaned:
                await c.execute(
                    text("UPDATE execution_intents SET consumed=true WHERE id=:id"),
                    {"id": intent["id"]},
                )
    for item in cancelled:
        async with db.transaction() as c:
            run = await one(c, "SELECT * FROM runs WHERE id=:id FOR UPDATE", id=item["id"])
            live = await one(
                c,
                "SELECT id FROM execution_intents WHERE run_id=:id AND dispatchable AND NOT consumed LIMIT 1",
                id=item["id"],
            )
            if not live and (not run["lease_until"] or run["lease_until"] <= await db_now(c)):
                await c.execute(
                    text("UPDATE runs SET status='cancelled',outcome='cancelled' WHERE id=:id"),
                    {"id": item["id"]},
                )
                await event(c, item["id"], "run.cancelled", {"cleanup": "runner confirmed"})


async def db_now(c):
    return (await one(c, "SELECT now() AS time"))["time"]


async def main():
    settings = Settings()
    db = Database(settings)
    owner = uuid4()
    async with httpx.AsyncClient(
        base_url=settings.runner_url,
        timeout=10,
        headers={"Authorization": f"Bearer {settings.runner_token}"},
        limits=httpx.Limits(max_connections=4, max_keepalive_connections=2),
    ) as http:
        try:
            while True:
                try:
                    await tick(db, HttpSandbox(http), owner)
                except (httpx.HTTPError, OSError) as error:
                    print(
                        f"dispatcher transient boundary error: {type(error).__name__}", flush=True
                    )
                await asyncio.sleep(0.5)
        finally:
            await db.close()


if __name__ == "__main__":
    asyncio.run(main())
