"""Measured local capacity and API responsiveness; no synthetic service substitutes."""

import asyncio
import json
import time
from pathlib import Path

import pytest
from reporeaper.db import many, one
from reporeaper_runner.worker import docker
from test_failures import environment
from test_gate import create, run_state, runner_state, slow_request, until

pytestmark = pytest.mark.gate


async def test_shared_capacity_and_resource_measurements(api, db, runner):
    replica = "reaper-gate-runner-b"
    code, output = await docker(
        "run",
        "-d",
        "--name",
        replica,
        "--network",
        "reporeaper_control",
        "--memory",
        "192m",
        "-v",
        "reporeaper_artifacts:/data/artifacts",
        *environment(),
        "reporeaper-controller:local",
        "python",
        "-m",
        "reporeaper_runner.worker",
    )
    assert code == 0, output
    requests = []
    try:
        requests = [await slow_request(runner, "slow_test") for _ in range(2)]
        await until(
            lambda: asyncio.gather(*(runner_state(runner, r.execution_id) for r in requests)),
            lambda states: sum(s["status"] == "running" for s in states) == 1,
        )
        samples = []
        maximum_reservations = 0
        for _ in range(20):
            async with db.transaction() as c:
                count = await one(c, "SELECT count(*) AS n FROM capacity_reservations")
            maximum_reservations = max(maximum_reservations, count["n"])
            assert count["n"] <= 1, "Two controllers must respect the SAME global slot"
            start = time.monotonic()
            response = await api.get("/api/v1/runs")
            samples.append((time.monotonic() - start) * 1000)
            assert response.status_code == 200
            await asyncio.sleep(0.1)
        for request in requests:
            await runner.post(f"/executions/{request.execution_id}/cancel")
        await until(
            lambda: asyncio.gather(*(runner_state(runner, r.execution_id) for r in requests)),
            lambda states: all(s["status"] == "cancelled" and s["cleaned"] for s in states),
            timeout=15,
        )
        a, b = await asyncio.gather(create(api), create(api, "typescript-boundary"))
        await until(
            lambda: asyncio.gather(run_state(api, a["id"]), run_state(api, b["id"])),
            lambda states: all(s["status"] == "needs_review" for s in states),
            timeout=120,
        )
        async with db.transaction() as c:
            durations = await many(
                c,
                """SELECT request->>'target' AS target,
                count(*) AS samples,round(avg((result->>'duration_seconds')::numeric),3) AS mean_seconds,
                round(max((result->>'duration_seconds')::numeric),3) AS max_seconds
                FROM runner.jobs WHERE status='completed' AND result IS NOT NULL
                AND run_id IN (:a,:b) GROUP BY request->>'target'""",
                a=a["id"],
                b=b["id"],
            )
            storage = await one(c, "SELECT pg_database_size(current_database()) AS database_bytes")
        code, stats = await docker("stats", "--no-stream", "--format", "{{json .}}", timeout=30)
        assert code == 0, stats
        resources = [json.loads(line) for line in stats.splitlines() if line.strip()]
        ordered = sorted(samples)
        report = {
            "schema_version": 1,
            "scope": "Curated local M0; no production throughput claim",
            "api_latency_samples": len(samples),
            "api_p50_ms": round(ordered[10], 2),
            "api_p95_ms": round(ordered[18], 2),
            "runner_controllers": 2,
            "configured_global_slots": 1,
            "observed_max_reservations": maximum_reservations,
            "execution_wall_time_includes_setup_and_cleanup": durations,
            "postgres": storage,
            "docker_stats": resources,
        }
        Path("/reports/resource-metrics.json").write_text(json.dumps(report, indent=2, default=str))
        assert report["api_p95_ms"] < 2000
    finally:
        for request in requests:
            await runner.post(f"/executions/{request.execution_id}/cancel")
        await docker("rm", "-f", replica)
