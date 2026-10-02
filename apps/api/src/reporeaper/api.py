import asyncio
import hashlib
import hmac
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from qdrant_client import AsyncQdrantClient
from sqlalchemy import text

from reporeaper.adapters import FileArtifacts
from reporeaper.config import Settings
from reporeaper.db import Database, command, encode, event, many, one
from reporeaper.domain import ErrorEnvelope, RunCreate, RunView
from reporeaper.seed import USER, WORKSPACE


@asynccontextmanager
async def lifespan(app):
    settings = Settings()
    app.state.settings = settings
    app.state.db = Database(settings)
    app.state.http = httpx.AsyncClient(timeout=5, limits=httpx.Limits(max_connections=8))
    app.state.qdrant = AsyncQdrantClient(url=settings.qdrant_url, timeout=5)
    app.state.artifacts = FileArtifacts(settings.artifact_root)
    yield
    await app.state.qdrant.close()
    await app.state.http.aclose()
    await app.state.db.close()


app = FastAPI(title="RepoReaper", version="1.0.0", lifespan=lifespan)


@app.exception_handler(HTTPException)
async def error_handler(request, error):
    return JSONResponse(
        status_code=error.status_code,
        content=ErrorEnvelope(
            code=f"http_{error.status_code}",
            message=str(error.detail),
            retryable=error.status_code in {429, 503},
            correlation_id=str(uuid4()),
        ).model_dump(),
    )


async def identity(request: Request):
    settings = request.app.state.settings
    origin = request.headers.get("origin")
    if origin and origin != settings.app_origin:
        raise HTTPException(403, "Origin is not authorized")
    cookie = request.cookies.get("reaper_session", "")
    expected = hmac.new(
        settings.session_secret.encode(), str(USER).encode(), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(cookie, expected):
        raise HTTPException(401, "Open the local demo session first")
    async with request.app.state.db.transaction() as c:
        member = await one(
            c,
            "SELECT role FROM memberships WHERE user_id=:u AND workspace_id=:w",
            u=USER,
            w=WORKSPACE,
        )
    if not member:
        raise HTTPException(403, "Workspace membership revoked")
    return USER, WORKSPACE


@app.get("/api/v1/session")
async def session(request: Request, response: Response):
    origin = request.headers.get("origin")
    if origin and origin != request.app.state.settings.app_origin:
        raise HTTPException(403, "Unauthorized origin")
    # Local-only bootstrap behind loopback-bound proxy. Hosted identity is not enabled.
    secret = request.app.state.settings.session_secret
    cookie = hmac.new(secret.encode(), str(USER).encode(), hashlib.sha256).hexdigest()
    response.set_cookie("reaper_session", cookie, httponly=True, samesite="strict")
    return {
        "user": "Local developer",
        "workspace_id": WORKSPACE,
        "mode": "deterministic_fixture",
        "publication_enabled": False,
    }


@app.get("/api/v1/health/live")
async def live():
    return {"status": "alive"}


@app.get("/api/v1/health/ready")
async def ready(request: Request):
    async with request.app.state.db.transaction() as c:
        await one(c, "SELECT 1")
    await request.app.state.qdrant.get_collections()
    return {"status": "ready", "mode": "deterministic_fixture"}


async def load_run(request, workspace, run_id):
    async with request.app.state.db.transaction() as c:
        run = await one(
            c,
            """SELECT r.*,s.commit_sha AS base_sha,s.manifest FROM runs r
            JOIN snapshots s ON s.id=r.snapshot_id WHERE r.id=:id AND r.workspace_id=:w""",
            id=run_id,
            w=workspace,
        )
    if not run:
        raise HTTPException(404, "Run not found in authorized workspace")
    return run


def view(run):
    return RunView(
        **{
            k: run[k]
            for k in (
                "id",
                "fixture",
                "title",
                "status",
                "outcome",
                "base_sha",
                "version",
                "graph_version",
                "latest_sequence",
                "patch",
                "patch_sha256",
                "evidence",
                "error",
            )
        },
        targets=run["manifest"]["targets"],
    )


@app.get("/api/v1/repositories")
async def repositories(request: Request, auth=Depends(identity)):
    async with request.app.state.db.transaction() as c:
        rows = await many(
            c,
            """SELECT r.id,r.name,r.fixture,s.commit_sha,s.manifest->'targets' AS targets
            FROM repositories r JOIN snapshots s ON s.repository_id=r.id WHERE r.workspace_id=:w""",
            w=auth[1],
        )
    return rows


@app.post("/api/v1/runs", status_code=202, response_model=RunView)
async def create_run(
    body: RunCreate,
    request: Request,
    auth=Depends(identity),
    idempotency_key: str = Header(min_length=1, max_length=128),
):
    if body.fault:
        raise HTTPException(
            422, "Fault injection is available only through the gate test control plane"
        )
    digest = hashlib.sha256(body.model_dump_json().encode()).hexdigest()
    run_id = uuid4()
    async with request.app.state.db.transaction() as c:
        # Serialize workspace admission and request-key creation across API replicas.
        await one(c, "SELECT id FROM workspaces WHERE id=:w FOR UPDATE", w=auth[1])
        existing = await one(
            c,
            "SELECT * FROM idempotency_keys WHERE workspace_id=:w AND actor_id=:u AND action='run.create' AND key=:key",
            w=auth[1],
            u=auth[0],
            key=idempotency_key,
        )
        if existing:
            if existing["body_hash"] != digest:
                raise HTTPException(409, "Idempotency key reused with different request")
            run_id = existing["result_id"]
        else:
            count = await one(
                c,
                "SELECT count(*) AS count FROM runs WHERE workspace_id=:w AND status IN ('queued','waiting_execution','investigating','preparing','verifying')",
                w=auth[1],
            )
            if count["count"] >= request.app.state.settings.queued_runs_per_workspace:
                raise HTTPException(429, "Workspace queue is full; retry after a run finishes")
            snapshot = await one(
                c,
                """SELECT s.id FROM snapshots s JOIN repositories r ON r.id=s.repository_id
                WHERE r.workspace_id=:w AND r.fixture=:fixture""",
                w=auth[1],
                fixture=body.fixture,
            )
            if not snapshot:
                raise HTTPException(422, "Select an approved fixture repository")
            await c.execute(
                text("""INSERT INTO runs(id,workspace_id,snapshot_id,fixture,title,description,configuration)
                VALUES(:id,:w,:snapshot,:fixture,:title,:description,CAST(:config AS jsonb))"""),
                dict(
                    id=run_id,
                    w=auth[1],
                    snapshot=snapshot["id"],
                    fixture=body.fixture,
                    title=body.title,
                    description=body.description,
                    config=encode(
                        {
                            "graph_version": "1",
                            "prompt_version": "fixture-1",
                            "model": "deterministic-v1",
                            "index_version": "fixture-hash-v1",
                            "profile_version": "1",
                            "runtime_images": {
                                "python": request.app.state.settings.python_image,
                                "node": request.app.state.settings.node_image,
                            },
                            "attempts": 1,
                        }
                    ),
                ),
            )
            await c.execute(
                text("INSERT INTO idempotency_keys VALUES(:w,:u,'run.create',:key,:hash,:run)"),
                dict(w=auth[1], u=auth[0], key=idempotency_key, hash=digest, run=run_id),
            )
            await event(
                c, run_id, "run.queued", {"mode": "deterministic_fixture", "fixture": body.fixture}
            )
            await command(c, run_id, "graph", f"start/{run_id}", {"graph_version": "1"})
    return view(await load_run(request, auth[1], run_id))


@app.get("/api/v1/runs", response_model=list[RunView])
async def runs(request: Request, auth=Depends(identity)):
    async with request.app.state.db.transaction() as c:
        rows = await many(
            c,
            """SELECT r.*,s.commit_sha AS base_sha,s.manifest FROM runs r
            JOIN snapshots s ON s.id=r.snapshot_id WHERE r.workspace_id=:w ORDER BY r.created_at DESC LIMIT 50""",
            w=auth[1],
        )
    return [view(row) for row in rows]


@app.get("/api/v1/runs/{run_id}", response_model=RunView)
async def run(run_id: UUID, request: Request, auth=Depends(identity)):
    return view(await load_run(request, auth[1], run_id))


@app.post("/api/v1/runs/{run_id}/cancel", status_code=202)
async def cancel(run_id: UUID, request: Request, auth=Depends(identity)):
    await load_run(request, auth[1], run_id)
    async with request.app.state.db.transaction() as c:
        row = await one(
            c,
            """UPDATE runs SET cancel_requested=true,status='cancelling'
            WHERE id=:id AND workspace_id=:w AND status NOT IN ('completed','cancelled','failed','needs_review') RETURNING id""",
            id=run_id,
            w=auth[1],
        )
        if not row:
            raise HTTPException(409, "Run is already terminal or awaiting review")
        await event(c, run_id, "run.cancellation_requested", {})
    return {"run_id": run_id, "status": "cancelling"}


@app.get("/api/v1/runs/{run_id}/evidence")
async def evidence(run_id: UUID, request: Request, auth=Depends(identity)):
    data = await load_run(request, auth[1], run_id)
    return {
        "base_sha": data["base_sha"],
        "executions": data["evidence"],
        "citations": [
            {
                "path": t["path"],
                "start_line": 1,
                "end_line": 3,
                "text": data["manifest"]["files"][t["path"]],
            }
            for t in data["manifest"]["targets"]
        ],
    }


@app.get("/api/v1/runs/{run_id}/patches")
async def patches(run_id: UUID, request: Request, auth=Depends(identity)):
    data = await load_run(request, auth[1], run_id)
    return (
        []
        if not data["patch"]
        else [{"id": run_id, "sha256": data["patch_sha256"], "base_sha": data["base_sha"]}]
    )


@app.get("/api/v1/patches/{patch_id}/diff")
async def diff(patch_id: UUID, request: Request, auth=Depends(identity)):
    data = await load_run(request, auth[1], patch_id)
    if not data["patch"]:
        raise HTTPException(404, "No patch yet")
    return Response(
        data["patch"],
        media_type="text/x-diff",
        headers={"Content-Disposition": 'attachment; filename="reporeaper.patch"'},
    )


@app.get("/api/v1/runs/{run_id}/events")
async def events(
    run_id: UUID,
    request: Request,
    auth=Depends(identity),
    last_event_id: int = Header(default=0),
    cursor: int = 0,
):
    await load_run(request, auth[1], run_id)

    async def stream():
        sequence = max(cursor, last_event_id)
        while not await request.is_disconnected():
            async with request.app.state.db.transaction() as c:
                rows = await many(
                    c,
                    "SELECT * FROM run_events WHERE run_id=:id AND sequence>:seq ORDER BY sequence LIMIT 100",
                    id=run_id,
                    seq=sequence,
                )
            for row in rows:
                sequence = row["sequence"]
                payload = {
                    "run_id": str(run_id),
                    "sequence": sequence,
                    "type": row["type"],
                    "schema_version": row["schema_version"],
                    "timestamp": row["created_at"].isoformat(),
                    "payload": row["payload"],
                }
                yield f"id: {sequence}\nevent: {row['type']}\ndata: {encode(payload)}\n\n"
            if not rows:
                yield ": heartbeat\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/v1/artifacts/{artifact_id}/download")
async def artifact(artifact_id: UUID, request: Request, auth=Depends(identity)):
    async with request.app.state.db.transaction() as c:
        row = await one(
            c, "SELECT * FROM artifacts WHERE id=:id AND workspace_id=:w", id=artifact_id, w=auth[1]
        )
    if not row:
        raise HTTPException(404, "Artifact not found")
    content = await request.app.state.artifacts.get(auth[1], row["object_key"])
    return Response(content, media_type="application/octet-stream")
