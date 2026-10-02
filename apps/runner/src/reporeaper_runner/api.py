import hmac
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from reporeaper.config import Settings
from reporeaper.db import Database, encode, one
from reporeaper.domain import ExecutionRequest, ExecutionResult
from reporeaper.fixtures import CATALOG
from sqlalchemy import text


@asynccontextmanager
async def lifespan(app):
    app.state.settings = Settings()
    app.state.db = Database(app.state.settings)
    yield
    await app.state.db.close()


app = FastAPI(title="RepoReaper private runner", lifespan=lifespan)


def authorize(request: Request, authorization: str = Header(default="")):
    if not hmac.compare_digest(authorization, f"Bearer {request.app.state.settings.runner_token}"):
        raise HTTPException(401, "Runner authorization required")


def result(row):
    return (
        ExecutionResult.model_validate(row["result"])
        if row["result"]
        else ExecutionResult(
            execution_id=row["id"], status=row["status"], cleaned=row["status"] == "cancelled"
        )
    )


@app.post("/executions", response_model=ExecutionResult, dependencies=[Depends(authorize)])
async def submit(body: ExecutionRequest, request: Request):
    if body.image_digest and body.image_digest not in {
        request.app.state.settings.python_image,
        request.app.state.settings.node_image,
    }:
        raise HTTPException(422, "Captured runtime digest is not approved")
    if body.fixture not in CATALOG or body.phase not in {
        "baseline",
        "patched",
        "slow_setup",
        "slow_test",
        "isolation",
    }:
        raise HTTPException(422, "Only curated fixture profiles may run")
    if body.target not in {t[0] for t in CATALOG[body.fixture] if t[3]}:
        raise HTTPException(422, "No approved execution profile for target")
    async with request.app.state.db.transaction() as c:
        await c.execute(
            text("""INSERT INTO runner.jobs(id,workspace_id,run_id,input_hash,request)
            VALUES(:id,:w,:run,:hash,CAST(:req AS jsonb)) ON CONFLICT(id) DO NOTHING"""),
            dict(
                id=body.execution_id,
                w=body.workspace_id,
                run=body.run_id,
                hash=body.input_hash,
                req=encode(body.model_dump(mode="json")),
            ),
        )
        row = await one(c, "SELECT * FROM runner.jobs WHERE id=:id", id=body.execution_id)
        if row["input_hash"] != body.input_hash or row["request"] != body.model_dump(mode="json"):
            raise HTTPException(409, "Execution identity already exists with different input")
    return result(row)


@app.get(
    "/executions/{execution_id}", response_model=ExecutionResult, dependencies=[Depends(authorize)]
)
async def status(execution_id: UUID, request: Request):
    async with request.app.state.db.transaction() as c:
        row = await one(c, "SELECT * FROM runner.jobs WHERE id=:id", id=execution_id)
    if not row:
        raise HTTPException(404, "Execution not yet submitted")
    return result(row)


@app.post(
    "/executions/{execution_id}/cancel",
    response_model=ExecutionResult,
    dependencies=[Depends(authorize)],
)
async def cancel(execution_id: UUID, request: Request):
    async with request.app.state.db.transaction() as c:
        row = await one(
            c,
            "UPDATE runner.jobs SET cancel_requested=true WHERE id=:id RETURNING *",
            id=execution_id,
        )
        if not row:
            raise HTTPException(404, "Execution not submitted")
        if row["status"] == "queued":
            row = await one(
                c,
                "UPDATE runner.jobs SET status='cancelled' WHERE id=:id RETURNING *",
                id=execution_id,
            )
    return result(row)
