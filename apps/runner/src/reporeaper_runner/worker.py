import asyncio
import json
import time
from uuid import uuid4

from reporeaper.adapters import FileArtifacts
from reporeaper.config import Settings
from reporeaper.db import Database, encode, many, one
from reporeaper.domain import ExecutionRequest, ExecutionResult
from reporeaper.fixtures import ROOT, manifest, patch_for, sha
from sqlalchemy import text


async def docker(*args, timeout=15):
    process = await asyncio.create_subprocess_exec(
        "docker", *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
    )
    try:
        async with asyncio.timeout(timeout):
            output, _ = await process.communicate()
    except TimeoutError:
        process.kill()
        await process.wait()
        raise
    return process.returncode, output.decode(errors="replace")[:65536]


async def reserve(db, owner, slots):
    async with db.transaction() as c:
        # Shared SQL lock+rows, never a per-process semaphore used as global capacity.
        await c.execute(text("SELECT pg_advisory_xact_lock(734911)"))
        # Expired reservations only reclaimed AFTER removing any orphan container.
        count = await one(c, "SELECT count(*) AS n FROM capacity_reservations")
        if count["n"] >= slots:
            return None
        job = await one(
            c,
            """SELECT * FROM runner.jobs WHERE status='queued' AND NOT cancel_requested
            ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1""",
        )
        if not job:
            return None
        await c.execute(
            text(
                "INSERT INTO capacity_reservations VALUES(:id,:owner,now()+interval '15 seconds')"
            ),
            dict(id=job["id"], owner=owner),
        )
        await c.execute(
            text(
                "UPDATE runner.jobs SET status='setup',owner=:owner,lease_until=now()+interval '15 seconds' WHERE id=:id"
            ),
            dict(id=job["id"], owner=owner),
        )
        return job


async def reap(db):
    async with db.transaction() as c:
        await c.execute(text("SELECT pg_advisory_xact_lock(734911)"))
        expired = await many(
            c, "SELECT execution_id,owner FROM capacity_reservations WHERE lease_until<now()"
        )
    for row in expired:
        # Keep shared capacity occupied until the sandbox is definitely removed.
        name = f"reaper-{row['execution_id']}-{row['owner']}"
        await docker("rm", "-f", name)
        code, absence = await docker("inspect", name)
        if not (
            code != 0
            and ("no such object" in absence.lower() or "no such container" in absence.lower())
        ):
            continue  # Daemon errors are not proof of cleanup; retain shared capacity.
        async with db.transaction() as c:
            await c.execute(
                text("""UPDATE runner.jobs SET status=CASE WHEN cancel_requested THEN 'cancelled' ELSE 'queued' END,
                owner=NULL,lease_until=NULL WHERE id=:id AND lease_until<now()"""),
                {"id": row["execution_id"]},
            )
            await c.execute(
                text(
                    "DELETE FROM capacity_reservations WHERE execution_id=:id AND lease_until<now()"
                ),
                {"id": row["execution_id"]},
            )


async def execute(db, settings, owner, job):
    req = ExecutionRequest.model_validate(job["request"])
    # Physical attempt names include ownership, so a stale controller cannot delete
    # a replacement sandbox after its reservation has been reclaimed.
    name = f"reaper-{req.execution_id}-{owner}"
    start = time.monotonic()
    image = req.image_digest or (
        settings.python_image if req.target == "python" else settings.node_image
    )
    approved = {settings.python_image, settings.node_image}
    result = ExecutionResult(
        execution_id=req.execution_id,
        status="environment_failure",
        source_hash=req.source_hash,
        patch_hash=req.patch_hash,
    )
    process = None
    output = bytearray()
    try:
        if req.image_digest and req.image_digest not in approved:
            raise ValueError("Requested captured runtime is not in the approved image registry")
        data = manifest(req.fixture)
        target = next(t for t in data["targets"] if t["id"] == req.target)
        source = data["files"][target["path"]]
        if sha(source.encode()) != req.source_hash:
            raise ValueError("Immutable source hash mismatch")
        if req.phase == "patched" and req.patch_hash != sha(
            patch_for(data["files"], data["targets"]).encode()
        ):
            raise ValueError("Patch hash mismatch")
        code, metadata = await docker("image", "inspect", image, "--format", "{{.Id}}")
        if code:
            raise RuntimeError("Approved runtime image is missing")
        result.image_digest = metadata.strip()
        harness = (
            ROOT
            / "evaluations"
            / "harness"
            / ("python_check.py" if req.target == "python" else "node_check.mjs")
        )
        result.harness_hash = sha(harness.read_bytes())
        argv = (
            ["python", "/opt/bootstrap.py"]
            if req.target == "python"
            else ["node", "/opt/bootstrap.mjs"]
        )
        # Image digest rather than mutable tag is used for actual execution.
        code, creation = await docker(
            "create",
            "--name",
            name,
            "--label",
            "reporeaper.sandbox=true",
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--user",
            "10001:10001",
            "--pids-limit",
            "64",
            "--memory",
            "256m",
            "--cpus",
            "1",
            "--tmpfs",
            "/work:rw,nosuid,nodev,size=16m,uid=10001,gid=10001",
            "--tmpfs",
            "/tmp:rw,nosuid,nodev,size=8m,uid=10001,gid=10001",
            "--log-driver",
            "local",
            "--log-opt",
            "max-size=1m",
            "--log-opt",
            "max-file=1",
            "--log-opt",
            "compress=false",
            result.image_digest,
            *argv,
            req.fixture,
            target["path"],
            req.phase,
        )
        if code:
            raise RuntimeError(creation)
        process = await asyncio.create_subprocess_exec(
            "docker",
            "start",
            "-a",
            name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        async def read():
            while chunk := await process.stdout.read(4096):
                if len(output) < 65536:
                    output.extend(chunk[: 65536 - len(output)])

        reader = asyncio.create_task(read())
        deadline = start + req.timeout_seconds
        last_heartbeat = 0.0
        while process.returncode is None:
            async with db.transaction() as c:
                await c.execute(text("SELECT pg_advisory_xact_lock(734911)"))
                row = await one(
                    c,
                    "SELECT cancel_requested,owner,lease_until>clock_timestamp() AS live FROM runner.jobs WHERE id=:id",
                    id=req.execution_id,
                )
                if row["owner"] != owner or not row["live"]:
                    raise RuntimeError("Runner ownership lost")
                if time.monotonic() - last_heartbeat > 2:
                    await c.execute(
                        text(
                            "UPDATE runner.jobs SET status='running',lease_until=now()+interval '15 seconds' WHERE id=:id AND owner=:owner"
                        ),
                        dict(id=req.execution_id, owner=owner),
                    )
                    await c.execute(
                        text(
                            "UPDATE capacity_reservations SET lease_until=now()+interval '15 seconds' WHERE execution_id=:id AND owner=:owner"
                        ),
                        dict(id=req.execution_id, owner=owner),
                    )
                    last_heartbeat = time.monotonic()
            if row["cancel_requested"] or time.monotonic() > deadline:
                result.status = "cancelled" if row["cancel_requested"] else "timed_out"
                await docker("rm", "-f", name)
                break
            await asyncio.sleep(0.2)
        await process.wait()
        await reader
        result.log = output.decode(errors="replace")
        if result.status not in {"cancelled", "timed_out"}:
            code, inspected = await docker("inspect", name, "--format", "{{json .State}}")
            state = json.loads(inspected) if not code else {}
            result.exit_code = state.get("ExitCode")
            result.status = (
                "completed"
                if result.exit_code is not None
                and not state.get("OOMKilled")
                and not state.get("Error")
                else "environment_failure"
            )
            result.expected_failure = (
                result.exit_code != 0 and "REAPER_EXPECTED_BOUNDARY_FAILURE" in result.log
            )
        result.toolchain = (
            "Python 3.12.14"
            if req.target == "python"
            else "Node.js 22.20.0 + TypeScript 5.9.3 strict check"
        )
    except Exception as error:
        result.log = f"{type(error).__name__}: {str(error)[:2000]}"
    finally:
        if process and process.returncode is None:
            process.kill()
            await process.wait()
        await docker("rm", "-f", name)
        code, absence = await docker("inspect", name)
        result.cleaned = code != 0 and (
            "no such object" in absence.lower() or "no such container" in absence.lower()
        )
        result.duration_seconds = time.monotonic() - start
        raw_log = result.log.encode()
        store = FileArtifacts(settings.artifact_root)
        object_key = await store.put(req.workspace_id, raw_log)
        artifact_id = uuid4()
        result.log_artifact_id = artifact_id
        result.log_sha256 = sha(raw_log)
        # Checkpoints carry references, not repository-emitted console text.
        result.log = ""
        async with db.transaction() as c:
            await c.execute(
                text(
                    "INSERT INTO artifacts(id,workspace_id,object_key,sha256,size) VALUES(:id,:w,:key,:hash,:size)"
                ),
                {
                    "id": artifact_id,
                    "w": req.workspace_id,
                    "key": object_key,
                    "hash": result.log_sha256,
                    "size": len(raw_log),
                },
            )
            await c.execute(
                text("""UPDATE runner.jobs SET status=:status,result=CAST(:result AS jsonb),
                owner=NULL,lease_until=NULL WHERE id=:id AND owner=:owner"""),
                dict(
                    id=req.execution_id,
                    owner=owner,
                    status=result.status,
                    result=encode(result.model_dump(mode="json")),
                ),
            )
            if result.cleaned:
                await c.execute(
                    text(
                        "DELETE FROM capacity_reservations WHERE execution_id=:id AND owner=:owner"
                    ),
                    dict(id=req.execution_id, owner=owner),
                )


async def main():
    settings, owner = Settings(), uuid4()
    db = Database(settings)
    try:
        while True:
            await reap(db)
            job = await reserve(db, owner, settings.sandbox_global_slots)
            if job:
                await execute(db, settings, owner, job)
            else:
                await asyncio.sleep(0.3)
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
