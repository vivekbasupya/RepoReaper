import asyncio
import json
from uuid import UUID, uuid4

import httpx
import pytest
from reporeaper.config import Settings
from reporeaper.db import command, encode, event, many, one
from reporeaper.seed import WORKSPACE
from reporeaper_runner.worker import docker
from sqlalchemy import text
from test_gate import create, run_state, runner_state, until

pytestmark = pytest.mark.gate


async def fault_run(db, point):
    run_id = uuid4()
    async with db.transaction() as c:
        snapshot = await one(
            c,
            """SELECT s.id FROM snapshots s JOIN repositories r ON r.id=s.repository_id
            WHERE r.workspace_id=:w AND r.fixture='python-boundary'""",
            w=WORKSPACE,
        )
        await c.execute(
            text("""INSERT INTO runs(id,workspace_id,snapshot_id,fixture,title,description,configuration)
            VALUES(:id,:w,:snapshot,'python-boundary','Gate crash probe','Trusted control plane',CAST(:config AS jsonb))"""),
            {
                "id": run_id,
                "w": WORKSPACE,
                "snapshot": snapshot["id"],
                "config": encode(
                    {"graph_version": "1", "profile_version": "1", "gate_crash": point}
                ),
            },
        )
        await event(c, run_id, "run.queued", {"gate_probe": point})
        await command(c, run_id, "graph", f"start/{run_id}", {"graph_version": "1"})
    return run_id


async def crash_fired(db, run_id):
    async with db.transaction() as c:
        return await one(c, "SELECT configuration FROM runs WHERE id=:id", id=run_id)


@pytest.mark.parametrize("point", ["after_intent", "after_checkpoint", "after_submission"])
async def test_04_worker_crash_replay_same_execution_id(api, db, point):
    run_id = await fault_run(db, point)
    await until(
        lambda: crash_fired(db, run_id), lambda r: r["configuration"].get("gate_fired") is True
    )
    async with db.transaction() as c:
        first = await one(
            c,
            "SELECT id,input_hash FROM execution_intents WHERE run_id=:id ORDER BY created_at LIMIT 1",
            id=run_id,
        )
    if point == "after_submission":
        # Dispatcher itself exited between remote persistence and marking delivery.
        await docker("start", "reporeaper-dispatcher-1")
    final = await until(
        lambda: run_state(api, run_id), lambda r: r["status"] == "needs_review", timeout=120
    )
    assert final["outcome"] == "verified_fix"
    async with db.transaction() as c:
        intents = await many(
            c,
            "SELECT id,input_hash FROM execution_intents WHERE run_id=:id ORDER BY created_at",
            id=run_id,
        )
        jobs = await many(c, "SELECT id FROM runner.jobs WHERE run_id=:id", id=run_id)
    assert len(intents) == len(jobs) == 2 and intents[0] == first


async def test_05_completion_before_wait_projection(api, db, runner):
    run_id = await fault_run(db, "after_checkpoint")
    await until(
        lambda: crash_fired(db, run_id), lambda r: r["configuration"].get("gate_fired") is True
    )
    async with db.transaction() as c:
        intent = await one(
            c,
            "SELECT * FROM execution_intents WHERE run_id=:id ORDER BY created_at LIMIT 1",
            id=run_id,
        )
    assert not intent["dispatchable"]
    # Trusted transport test delivers the same recorded intent during the crash window.
    response = await runner.post("/executions", json=intent["request"])
    assert response.status_code == 200
    await until(lambda: runner_state(runner, intent["id"]), lambda r: r["status"] == "completed")
    final = await until(
        lambda: run_state(api, run_id), lambda r: r["status"] == "needs_review", timeout=120
    )
    assert final["outcome"] == "verified_fix"
    assert final["evidence"][0]["execution_id"] == str(intent["id"])


async def test_06_recreate_empty_redis_recovers_durable_commands(api, db):
    # Stop the single graph worker so accepted work is pending when broker state vanishes.
    await docker("stop", "-t", "5", "reporeaper-graph-1")
    run = await create(api)
    try:
        code, original = await docker("inspect", "reporeaper-redis-1")
        assert code == 0
        inspected = json.loads(original)[0]
        labels = inspected["Config"]["Labels"]
        label_args = [arg for key, value in labels.items() for arg in ("--label", f"{key}={value}")]
        await docker("rm", "-f", "reporeaper-redis-1")
        code, output = await docker(
            "run",
            "-d",
            "--name",
            "reporeaper-redis-1",
            "--network",
            "reporeaper_control",
            "--network-alias",
            "redis",
            "--memory",
            str(inspected["HostConfig"]["Memory"] or 67108864),
            *label_args,
            "--health-cmd",
            "redis-cli ping",
            "--health-interval",
            "2s",
            "--health-timeout",
            "3s",
            "--health-retries",
            "30",
            "redis:7.4.5-alpine",
            "redis-server",
            "--maxmemory",
            "48mb",
            "--maxmemory-policy",
            "noeviction",
        )
        assert code == 0, output
    finally:
        await docker("start", "reporeaper-graph-1")
    final = await until(
        lambda: run_state(api, run["id"]), lambda r: r["status"] == "needs_review", timeout=120
    )
    assert final["outcome"] == "verified_fix"
    async with db.transaction() as c:
        jobs = await many(c, "SELECT id FROM runner.jobs WHERE run_id=:id", id=UUID(run["id"]))
    assert len(jobs) == 2


def environment():
    settings = Settings()
    return [
        part
        for key in (
            "database_url",
            "checkpoint_url",
            "redis_url",
            "qdrant_url",
            "runner_url",
            "runner_token",
            "session_secret",
            "app_origin",
            "python_image",
            "node_image",
        )
        for part in ("-e", f"{key.upper()}={getattr(settings, key)}")
    ]


async def start_replica(name, image, argv):
    code, output = await docker(
        "run",
        "-d",
        "--name",
        name,
        "--network",
        "reporeaper_control",
        "--memory",
        "384m",
        *environment(),
        image,
        *argv,
    )
    assert code == 0, output


async def test_08_two_apis_two_graph_workers_ownership(api, db):
    code, image = await docker("inspect", "reporeaper-api-1", "--format", "{{.Config.Image}}")
    assert code == 0
    await docker("stop", "-t", "5", "reporeaper-graph-1")
    names = ["reaper-gate-api-a", "reaper-gate-api-b", "reaper-gate-graph-a", "reaper-gate-graph-b"]
    try:
        for name in names[:2]:
            await start_replica(
                name,
                image.strip(),
                ["uvicorn", "reporeaper.api:app", "--host", "0.0.0.0", "--port", "8000"],
            )
        for name in names[2:]:
            await start_replica(
                name,
                image.strip(),
                [
                    "celery",
                    "-A",
                    "reporeaper.worker:celery",
                    "worker",
                    "--pool=prefork",
                    "--concurrency=1",
                    "-Q",
                    "graph",
                    "--loglevel=WARNING",
                ],
            )
        async with (
            httpx.AsyncClient(base_url="http://reaper-gate-api-a:8000", timeout=10) as a,
            httpx.AsyncClient(base_url="http://reaper-gate-api-b:8000", timeout=10) as b,
        ):

            async def boot(client):
                try:
                    return (await client.get("/api/v1/session")).status_code == 200
                except httpx.HTTPError:
                    return False

            await until(lambda: boot(a), bool)
            await until(lambda: boot(b), bool)
            key = str(uuid4())
            first, second = await asyncio.gather(create(a, key=key), create(b, key=key))
            assert first["id"] == second["id"]
            final = await until(
                lambda: run_state(a, first["id"]), lambda r: r["status"] == "needs_review"
            )
            assert final["outcome"] == "verified_fix"
            async with db.transaction() as c:
                intents = await many(
                    c, "SELECT id FROM execution_intents WHERE run_id=:id", id=UUID(first["id"])
                )

            async def released():
                async with db.transaction() as c:
                    return await one(
                        c, "SELECT fence,lease_owner FROM runs WHERE id=:id", id=UUID(first["id"])
                    )

            # Product review is committed before the bounded segment closes its saver.
            # Check actual release, rather than racing that final shutdown interval.
            state = await until(released, lambda row: row["lease_owner"] is None, timeout=5)
            assert len(intents) == 2 and state["fence"] >= 3 and state["lease_owner"] is None
    finally:
        for name in names:
            await docker("rm", "-f", name)
        await docker("start", "reporeaper-graph-1")


async def test_10_paused_v1_survives_new_build(api, db):
    await docker("stop", "-t", "5", "reporeaper-runner-worker-1")
    run = await create(api)
    await until(lambda: run_state(api, run["id"]), lambda r: r["status"] == "waiting_execution")
    await docker("stop", "-t", "5", "reporeaper-graph-1")
    name = "reaper-gate-upgrade"
    try:
        # Build a new image with a deployment version while retaining graph v1 implementation.
        process = await asyncio.create_subprocess_exec(
            "docker",
            "build",
            "-t",
            "reporeaper-upgrade:gate",
            "-",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        output, _ = await process.communicate(
            b"FROM reporeaper-backend:local\nENV BUILD_VERSION=2\n"
        )
        assert process.returncode == 0, output.decode()[-2000:]
        await start_replica(
            name,
            "reporeaper-upgrade:gate",
            [
                "celery",
                "-A",
                "reporeaper.worker:celery",
                "worker",
                "--pool=prefork",
                "--concurrency=1",
                "-Q",
                "graph",
                "--loglevel=WARNING",
            ],
        )
        await docker("start", "reporeaper-runner-worker-1")
        final = await until(
            lambda: run_state(api, run["id"]), lambda r: r["status"] == "needs_review"
        )
        assert final["graph_version"] == "1" and final["outcome"] == "verified_fix"
    finally:
        await docker("rm", "-f", name)
        await docker("start", "reporeaper-graph-1", "reporeaper-runner-worker-1")
