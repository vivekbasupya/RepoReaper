import asyncio
from uuid import UUID, uuid4

from celery import Celery
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import Command
from sqlalchemy import text

from reporeaper.config import Settings
from reporeaper.db import Database, command, event, fence, one
from reporeaper.faults import crash_once
from reporeaper.fixtures import DeterministicModel
from reporeaper.graph import GraphV1

# Configuration has no event-loop objects or connection pools before prefork.
settings = Settings()
celery = Celery("reporeaper", broker=settings.redis_url)
celery.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_time_limit=45,
    task_soft_time_limit=40,
    broker_transport_options={"visibility_timeout": 120},
    task_default_queue="graph",
    broker_connection_retry_on_startup=True,
)


@celery.task(name="reporeaper.segment")
def segment(command_id: str):
    asyncio.run(process(UUID(command_id)))


async def process(command_id: UUID):
    db = Database(Settings())
    owner = uuid4()
    # A session advisory lock also serializes LangGraph checkpoint writes: stale lease
    # owners cannot overlap a takeover's saver. Never hold a SQL transaction during graph I/O.
    lock_connection = await db.engine.connect()
    run_id = None
    token = None
    try:
        async with db.transaction() as c:
            cmd = await one(c, "SELECT * FROM outbox WHERE id=:id", id=command_id)
        if not cmd or cmd["completed_at"]:
            return
        run_id = cmd["run_id"]
        locked = await one(
            lock_connection,
            "SELECT pg_try_advisory_lock(hashtextextended(:id,0)) AS ok",
            id=str(run_id),
        )
        await lock_connection.commit()
        if not locked["ok"]:
            return
        async with db.transaction() as c:
            run = await one(
                c,
                """UPDATE runs SET lease_owner=:owner,lease_until=now()+interval '60 seconds',
                fence=fence+1 WHERE id=:id AND (lease_until IS NULL OR lease_until<now()) RETURNING *""",
                id=run_id,
                owner=owner,
            )
            if not run:
                return
            token = run["fence"]
            if any(
                not value.startswith("sha256:")
                for value in run["configuration"].get("runtime_images", {}).values()
            ):
                await c.execute(
                    text(
                        "UPDATE runs SET status='waiting_input',error='Captured runtime uses a mutable tag; restart this run with pinned profiles' WHERE id=:id"
                    ),
                    {"id": run_id},
                )
                await finish_command(c, command_id)
                return
            if cmd["payload"].get("schema_version") != 1 or run["graph_version"] != "1":
                await c.execute(
                    text(
                        "UPDATE outbox SET error='Unsupported command/graph version',completed_at=now() WHERE id=:id"
                    ),
                    {"id": command_id},
                )
                await c.execute(
                    text(
                        "UPDATE runs SET status='waiting_input',error='Incompatible version: restart/export required' WHERE id=:id"
                    ),
                    {"id": run_id},
                )
                return
            await c.execute(
                text("""INSERT INTO command_receipts VALUES(:id,:owner,now()+interval '60 seconds',NULL)
                ON CONFLICT(command_id) DO UPDATE SET owner=:owner,lease_until=excluded.lease_until"""),
                dict(id=command_id, owner=owner),
            )
            if run["cancel_requested"] or run["status"] in {
                "needs_review",
                "completed",
                "cancelled",
                "failed",
            }:
                await finish_command(c, command_id)
                return
            snapshot = await one(
                c, "SELECT manifest FROM snapshots WHERE id=:id", id=run["snapshot_id"]
            )
        config = {"configurable": {"thread_id": str(run_id), "checkpoint_ns": ""}}
        async with AsyncPostgresSaver.from_conn_string(Settings().checkpoint_url) as saver:
            graph = GraphV1(
                db, run, owner, token, snapshot["manifest"], DeterministicModel()
            ).compile(saver)
            state = await graph.aget_state(config)
            graph_input = {"run_id": str(run_id), "graph_version": "1", "stage": 0, "evidence": []}
            if state.values:
                pending = state.values.get("pending_intent")
                async with db.transaction() as c:
                    intent = (
                        await one(
                            c, "SELECT * FROM execution_intents WHERE id=:id", id=UUID(pending)
                        )
                        if pending
                        else None
                    )
                if state.tasks and any(t.interrupts for t in state.tasks):
                    if not intent or not intent["result"]:
                        await project_wait(db, run, owner, token, state, command_id)
                        return
                    request = intent["request"]
                    if cmd["payload"].get("execution_id") and (
                        cmd["payload"]["execution_id"] != pending
                        or cmd["payload"].get("checkpoint_id") != intent["required_checkpoint_id"]
                        or state.config["configurable"]["checkpoint_id"]
                        != intent["required_checkpoint_id"]
                    ):
                        async with db.transaction() as c:
                            await finish_command(c, command_id)
                        return
                    result = {
                        **intent["result"],
                        "phase": request["phase"],
                        "target": request["target"],
                    }
                    graph_input = Command(resume=result)
                else:
                    graph_input = None  # Continue a crash between saved nodes.
            async with asyncio.timeout(25):
                await graph.ainvoke(graph_input, config)
            state = await graph.aget_state(config)
            await crash_once(db, run_id, "after_checkpoint")
            await project_wait(db, run, owner, token, state, command_id)
    finally:
        if run_id and token:
            async with db.transaction() as c:
                await c.execute(
                    text("""UPDATE runs SET lease_owner=NULL,lease_until=NULL
                    WHERE id=:id AND lease_owner=:owner AND fence=:token"""),
                    dict(id=run_id, owner=owner, token=token),
                )
        await lock_connection.close()  # Session advisory lock released on connection close.
        # Pooled connections require explicit unlock before reuse; engine disposal closes all.
        await db.close()


async def finish_command(c, command_id):
    await c.execute(text("UPDATE outbox SET completed_at=now() WHERE id=:id"), {"id": command_id})
    await c.execute(
        text("UPDATE command_receipts SET completed_at=now() WHERE command_id=:id"),
        {"id": command_id},
    )


async def project_wait(db, run, owner, token, state, command_id):
    async with db.transaction() as c:
        await fence(c, run["id"], owner, token)
        if state.tasks and any(t.interrupts for t in state.tasks):
            intent_id = UUID(state.values["pending_intent"])
            checkpoint = state.config["configurable"]["checkpoint_id"]
            await c.execute(
                text("""UPDATE execution_intents SET required_checkpoint_id=:cp,
                dispatchable=true WHERE id=:id AND graph_version='1'"""),
                dict(id=intent_id, cp=checkpoint),
            )
            await c.execute(
                text("""UPDATE execution_intents SET consumed=true WHERE run_id=:run
                AND id<>:id AND result IS NOT NULL"""),
                dict(run=run["id"], id=intent_id),
            )
            await c.execute(
                text(
                    "UPDATE runs SET status='waiting_execution',pending_intent=:intent WHERE id=:id"
                ),
                dict(id=run["id"], intent=intent_id),
            )
            await event(c, run["id"], "execution.waiting", {"execution_id": str(intent_id)})
            await command(
                c,
                run["id"],
                "execute",
                f"execute/{intent_id}",
                {"execution_id": str(intent_id), "checkpoint_id": checkpoint, "graph_version": "1"},
            )
        else:
            await c.execute(
                text(
                    "UPDATE execution_intents SET consumed=true WHERE run_id=:run AND result IS NOT NULL"
                ),
                {"run": run["id"]},
            )
        await finish_command(c, command_id)
