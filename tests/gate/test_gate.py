"""Real service tests. Never skip or substitute persistence/queue/runner mocks."""

import asyncio
import time
from uuid import UUID, uuid4

import pytest
from qdrant_client import AsyncQdrantClient
from reporeaper.adapters import Retrieval
from reporeaper.config import Settings
from reporeaper.db import LostLease, fence, many, one
from reporeaper.domain import ExecutionRequest
from reporeaper.fixtures import manifest, sha
from reporeaper.seed import OTHER_WORKSPACE, WORKSPACE
from reporeaper_runner.worker import docker
from sqlalchemy import text

pytestmark = pytest.mark.gate


async def create(api, fixture="python-boundary", key=None):
    response = await api.post(
        "/api/v1/runs", json={"fixture": fixture}, headers={"Idempotency-Key": key or str(uuid4())}
    )
    assert response.status_code == 202, response.text
    return response.json()


async def until(call, predicate, timeout=90):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = await call()
        if predicate(result):
            return result
        await asyncio.sleep(0.3)
    raise AssertionError(f"Timed out; last observed state: {result}")


async def run_state(api, run_id):
    response = await api.get(f"/api/v1/runs/{run_id}")
    response.raise_for_status()
    return response.json()


@pytest.mark.parametrize("fixture", ["python-boundary", "typescript-boundary"])
async def test_01_two_language_real_review(api, db, fixture):
    run = await create(api, fixture)
    final = await until(lambda: run_state(api, run["id"]), lambda r: r["status"] == "needs_review")
    assert final["outcome"] == "verified_fix", final
    assert len(final["evidence"]) == 2
    baseline, patched = final["evidence"]
    assert baseline["exit_code"] != 0 and baseline["expected_failure"]
    assert patched["exit_code"] == 0 and patched["cleaned"]
    assert baseline["source_hash"] == patched["source_hash"]
    assert patched["patch_hash"] == final["patch_sha256"]
    assert all(
        e["image_digest"].startswith("sha256:") and e["harness_hash"] for e in final["evidence"]
    )
    if fixture == "typescript-boundary":
        log = await api.get(f"/api/v1/artifacts/{patched['log_artifact_id']}/download")
        assert log.status_code == 200 and "Trusted TypeScript strict check passed" in log.text
    async with db.transaction() as c:
        jobs = await many(c, "SELECT id FROM runner.jobs WHERE run_id=:id", id=UUID(run["id"]))
        intents = await many(
            c, "SELECT * FROM execution_intents WHERE run_id=:id", id=UUID(run["id"])
        )
    assert len(jobs) == len(intents) == 2 and all(i["required_checkpoint_id"] for i in intents)
    assert (await api.get(f"/api/v1/patches/{run['id']}/diff")).status_code == 200


async def test_02_mixed_project_cannot_claim_full_verification(api):
    run = await create(api, "mixed-boundary")
    final = await until(lambda: run_state(api, run["id"]), lambda r: r["status"] == "needs_review")
    assert final["outcome"] == "partial_verification"
    assert {t["id"] for t in final["targets"]} == {"python", "tsx"}
    assert any(t["profile"] is None for t in final["targets"])
    assert "frontend/bounds.tsx" in final["patch"]


async def test_03_wait_releases_single_graph_worker(api, db, runner):
    # Occupy the single shared sandbox slot with an authenticated slow trusted profile.
    blocker = await slow_request(runner, "slow_test")
    await until(
        lambda: runner_state(runner, blocker.execution_id), lambda r: r["status"] == "running"
    )
    a, b = await asyncio.gather(create(api), create(api, "typescript-boundary"))
    states = await until(
        lambda: asyncio.gather(run_state(api, a["id"]), run_state(api, b["id"])),
        lambda rows: all(r["status"] == "waiting_execution" for r in rows),
    )
    assert all(r["latest_sequence"] >= 2 for r in states)
    async with db.transaction() as c:
        rows = await many(
            c, "SELECT lease_owner FROM runs WHERE id IN (:a,:b)", a=UUID(a["id"]), b=UUID(b["id"])
        )
    assert all(r["lease_owner"] is None for r in rows)
    await runner.post(f"/executions/{blocker.execution_id}/cancel")
    await until(lambda: run_state(api, b["id"]), lambda r: r["status"] == "needs_review")


async def test_idempotency_and_fencing(api, db):
    key = str(uuid4())
    a, b = await asyncio.gather(create(api, key=key), create(api, key=key))
    assert a["id"] == b["id"]
    response = await api.post(
        "/api/v1/runs", json={"fixture": "typescript-boundary"}, headers={"Idempotency-Key": key}
    )
    assert response.status_code == 409
    async with db.transaction() as c:
        with pytest.raises(LostLease):
            await fence(c, UUID(a["id"]), uuid4(), -1)


async def runner_state(runner, execution_id):
    response = await runner.get(f"/executions/{execution_id}")
    assert response.status_code == 200, response.text
    return response.json()


async def slow_request(runner, phase, workspace_id=WORKSPACE):
    data = manifest("python-boundary")
    request = ExecutionRequest(
        execution_id=uuid4(),
        workspace_id=workspace_id,
        run_id=uuid4(),
        fixture="python-boundary",
        target="python",
        phase=phase,
        input_hash=sha(str(uuid4()).encode()),
        source_hash=sha(data["files"]["bounds.py"].encode()),
        timeout_seconds=30,
    )
    response = await runner.post("/executions", json=request.model_dump(mode="json"))
    assert response.status_code == 200, response.text
    return request


@pytest.mark.parametrize("phase", ["slow_setup", "slow_test"])
async def test_07_runner_cancellation_reclaims_reservations(db, runner, phase):
    request = await slow_request(runner, phase)
    await until(
        lambda: runner_state(runner, request.execution_id), lambda r: r["status"] == "running"
    )

    async def child_started():
        code, names = await docker(
            "ps", "--filter", f"name=reaper-{request.execution_id}", "--format", "{{.Names}}"
        )
        if code or not names.strip():
            return False
        code, processes = await docker("top", names.strip(), "-eo", "pid,args")
        return code == 0 and "time.sleep(120)" in processes

    try:
        await until(child_started, bool, timeout=8)
    except BaseException:
        await runner.post(f"/executions/{request.execution_id}/cancel")
        raise
    started = time.monotonic()
    await runner.post(f"/executions/{request.execution_id}/cancel")
    final = await until(
        lambda: runner_state(runner, request.execution_id),
        lambda r: r["status"] == "cancelled" and r["cleaned"],
        timeout=10,
    )
    assert time.monotonic() - started < 10 and final["cleaned"]
    code, remaining = await docker(
        "ps", "-a", "--filter", f"name=reaper-{request.execution_id}", "--format", "{{.ID}}"
    )
    assert code == 0 and not remaining.strip(), (
        "Sandbox PID namespace/disk must actually be removed"
    )
    async with db.transaction() as c:
        assert (
            await one(
                c,
                "SELECT * FROM capacity_reservations WHERE execution_id=:id",
                id=request.execution_id,
            )
            is None
        )


async def test_09_real_vector_workspace_isolation_and_sandbox(runner, db, api):
    async with db.transaction() as c:
        foreign = await one(
            c, "SELECT id FROM snapshots WHERE workspace_id=:w LIMIT 1", w=OTHER_WORKSPACE
        )
    q = AsyncQdrantClient(url=Settings().qdrant_url)
    try:
        result = await Retrieval(q).search(WORKSPACE, foreign["id"], [0.1] * 8)
        assert result.points == []
    finally:
        await q.close()
    response = await api.get(f"/api/v1/artifacts/{uuid4()}/download")
    assert response.status_code == 404
    request = await slow_request(runner, "isolation")
    final = await until(
        lambda: runner_state(runner, request.execution_id), lambda r: r["status"] == "completed"
    )
    assert final["exit_code"] == 0
    assert final["log_artifact_id"] and final["log_sha256"]
    log = await api.get(f"/api/v1/artifacts/{final['log_artifact_id']}/download")
    assert log.status_code == 200 and "Isolation probe passed" in log.text
    foreign_request = await slow_request(runner, "isolation", workspace_id=OTHER_WORKSPACE)
    foreign_result = await until(
        lambda: runner_state(runner, foreign_request.execution_id),
        lambda r: r["status"] == "completed",
    )
    assert foreign_result["log_artifact_id"]
    denied = await api.get(f"/api/v1/artifacts/{foreign_result['log_artifact_id']}/download")
    assert denied.status_code == 404
    assert (
        await runner.get(
            "/executions/" + str(request.execution_id), headers={"Authorization": "Bearer forged"}
        )
    ).status_code == 401


async def test_durable_command_redelivery_after_lost_delivery(api, db):
    run = await create(api)
    # Pretend delivery was attempted: business work must still be recovered from SQL.
    async with db.transaction() as c:
        await c.execute(
            text(
                "UPDATE outbox SET published_at=now()-interval '10 seconds' WHERE run_id=:run AND completed_at IS NULL"
            ),
            {"run": UUID(run["id"])},
        )
    final = await until(lambda: run_state(api, run["id"]), lambda r: r["status"] == "needs_review")
    assert final["outcome"] == "verified_fix"
