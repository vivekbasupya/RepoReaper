"""Version 1 stays executable while paused runs exist. All side effects are durable-keyed."""

from typing import Any, TypedDict
from uuid import UUID, uuid5

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from sqlalchemy import text

from reporeaper.db import Database, encode, event, fence, one
from reporeaper.domain import ExecutionRequest, ModelAdapter
from reporeaper.faults import crash_once
from reporeaper.fixtures import sha


class State(TypedDict, total=False):
    run_id: str
    graph_version: str
    pending_intent: str
    stage: int
    evidence: list[dict[str, Any]]
    review: bool


class GraphV1:
    def __init__(
        self, db: Database, run: dict, owner: UUID, token: int, manifest: dict, model: ModelAdapter
    ):
        self.db, self.run, self.owner, self.token, self.manifest = db, run, owner, token, manifest
        self.run_id = run["id"]
        self.model = model
        self.plan = [
            (t, phase)
            for phase in ("baseline", "patched")
            for t in manifest["targets"]
            if t["profile"]
        ]

    async def prepare(self, state: State) -> dict:
        stage = state.get("stage", 0)
        target, phase = self.plan[stage]
        source = self.manifest["files"][target["path"]]
        diff = await self.model.propose(
            self.run["fixture"], self.manifest["files"], self.manifest["targets"]
        )
        logical = f"v1/{stage}/{target['id']}/{phase}/attempt-1"
        digest = sha(
            encode(
                {
                    "fixture": self.run["fixture"],
                    "target": target["id"],
                    "phase": phase,
                    "base": self.manifest["base_sha"],
                    "patch": sha(diff.encode()) if phase == "patched" else None,
                }
            ).encode()
        )
        intent_id = uuid5(self.run_id, logical)
        request = ExecutionRequest(
            execution_id=intent_id,
            workspace_id=self.run["workspace_id"],
            run_id=self.run_id,
            fixture=self.run["fixture"],
            target=target["id"],
            phase=phase,
            input_hash=digest,
            source_hash=sha(source.encode()),
            patch_hash=sha(diff.encode()) if phase == "patched" else None,
            timeout_seconds=30,
            image_digest=self.run["configuration"].get("runtime_images", {}).get(target["profile"]),
        )
        async with self.db.transaction() as c:
            await fence(c, self.run_id, self.owner, self.token)
            await c.execute(
                text("""INSERT INTO execution_intents
                (id,workspace_id,run_id,logical_step,input_hash,request,graph_version)
                VALUES(:id,:w,:run,:key,:hash,CAST(:req AS jsonb),'1') ON CONFLICT(run_id,logical_step) DO NOTHING"""),
                dict(
                    id=intent_id,
                    w=self.run["workspace_id"],
                    run=self.run_id,
                    key=logical,
                    hash=digest,
                    req=encode(request.model_dump(mode="json")),
                ),
            )
            existing = await one(
                c, "SELECT input_hash FROM execution_intents WHERE id=:id", id=intent_id
            )
            if existing["input_hash"] != digest:
                raise ValueError("Logical operation input changed on replay")
            if phase == "patched":
                await c.execute(
                    text("UPDATE runs SET patch=:diff,patch_sha256=:hash WHERE id=:id"),
                    dict(id=self.run_id, diff=diff, hash=sha(diff.encode())),
                )
        await crash_once(self.db, self.run_id, "after_intent")
        return {"pending_intent": str(intent_id), "stage": stage}

    async def wait(self, state: State) -> dict:
        # Node replay has no external side effects before interrupt.
        result = interrupt({"execution_id": state["pending_intent"], "graph_version": "1"})
        if result["execution_id"] != state["pending_intent"]:
            raise ValueError("Resume does not match pending execution")
        evidence = [*state.get("evidence", []), result]
        async with self.db.transaction() as c:
            await fence(c, self.run_id, self.owner, self.token)
            intent = await one(
                c,
                "SELECT consumed FROM execution_intents WHERE id=:id",
                id=UUID(state["pending_intent"]),
            )
            await c.execute(
                text("UPDATE runs SET evidence=CAST(:evidence AS jsonb) WHERE id=:id"),
                {"id": self.run_id, "evidence": encode(evidence)},
            )
            if not intent["consumed"]:
                await event(
                    c,
                    self.run_id,
                    "execution.completed",
                    {
                        "execution_id": result["execution_id"],
                        "phase": result["phase"],
                        "exit_code": result["exit_code"],
                    },
                )
                await c.execute(
                    text("UPDATE execution_intents SET consumed=true WHERE id=:id"),
                    {"id": UUID(state["pending_intent"])},
                )
        return {"evidence": evidence, "stage": state.get("stage", 0) + 1}

    def route(self, state: State) -> str:
        return "prepare" if state["stage"] < len(self.plan) else "review"

    async def review(self, state: State) -> dict:
        evidence = state["evidence"]
        baseline = [r for r in evidence if r["phase"] == "baseline"]
        patched = [r for r in evidence if r["phase"] == "patched"]
        reproduced = bool(baseline) and all(
            r["status"] == "completed" and r["expected_failure"] and r["exit_code"] != 0
            for r in baseline
        )
        passed = bool(patched) and all(
            r["status"] == "completed" and r["exit_code"] == 0 for r in patched
        )
        missing = any(t["profile"] is None for t in self.manifest["targets"])
        if any(r["status"] in {"environment_failure", "timed_out"} for r in evidence):
            outcome = "environment_failure"
        elif not reproduced:
            outcome = "not_reproduced"
        elif passed and not missing:
            outcome = "verified_fix"
        elif passed:
            outcome = "partial_verification"
        else:
            outcome = "unverified_patch"
        async with self.db.transaction() as c:
            await fence(c, self.run_id, self.owner, self.token)
            await c.execute(
                text("""UPDATE runs SET status='needs_review',outcome=:outcome,
                evidence=CAST(:evidence AS jsonb),pending_intent=NULL WHERE id=:id"""),
                dict(id=self.run_id, outcome=outcome, evidence=encode(evidence)),
            )
            await event(
                c,
                self.run_id,
                "review.ready",
                {
                    "outcome": outcome,
                    "limitations": [
                        "Curated deterministic model; fixture harness coverage only",
                        *(["React target has no executable profile in M0"] if missing else []),
                    ],
                },
            )
        return {"review": True}

    def compile(self, saver):
        graph = StateGraph(State)
        graph.add_node("prepare", self.prepare)
        graph.add_node("wait", self.wait)
        graph.add_node("review", self.review)
        graph.add_edge(START, "prepare")
        graph.add_edge("prepare", "wait")
        graph.add_conditional_edges("wait", self.route)
        graph.add_edge("review", END)
        return graph.compile(checkpointer=saver)
