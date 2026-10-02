import hashlib
from pathlib import Path
from uuid import UUID

import anyio
import httpx
from qdrant_client import AsyncQdrantClient, models

from reporeaper.domain import ExecutionRequest, ExecutionResult


class HttpSandbox:
    def __init__(self, http: httpx.AsyncClient):
        self.http = http

    async def submit(self, request: ExecutionRequest) -> ExecutionResult:
        response = await self.http.post("/executions", json=request.model_dump(mode="json"))
        response.raise_for_status()
        return ExecutionResult.model_validate(response.json())

    async def status(self, execution_id: UUID) -> ExecutionResult:
        response = await self.http.get(f"/executions/{execution_id}")
        response.raise_for_status()
        return ExecutionResult.model_validate(response.json())

    async def cancel(self, execution_id: UUID) -> ExecutionResult:
        response = await self.http.post(f"/executions/{execution_id}/cancel")
        response.raise_for_status()
        return ExecutionResult.model_validate(response.json())


class FileArtifacts:
    def __init__(self, root: str):
        self.root = Path(root)
        self.limiter = anyio.CapacityLimiter(4)

    async def put(self, workspace_id: UUID, content: bytes) -> str:
        if len(content) > 1_000_000:
            raise ValueError("Artifact exceeds M0 1MB limit")
        digest = hashlib.sha256(content).hexdigest()
        key = f"{workspace_id}/{digest}"

        def write():
            path = self.root / key
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                path.write_bytes(content)

        await anyio.to_thread.run_sync(write, limiter=self.limiter)
        return key

    async def get(self, workspace_id: UUID, key: str) -> bytes:
        parts = key.split("/")
        if len(parts) != 2 or parts[0] != str(workspace_id) or len(parts[1]) != 64:
            raise PermissionError("Artifact scope mismatch")
        if any(ch not in "0123456789abcdef" for ch in parts[1]):
            raise PermissionError("Invalid object key")
        return await anyio.to_thread.run_sync((self.root / key).read_bytes, limiter=self.limiter)


class FixtureEmbedding:
    version = "fixture-hash-v1"
    dimensions = 8

    async def embed(self, texts: list[str]) -> list[list[float]]:
        # Deliberately nonsemantic; only used to prove real filtered Qdrant I/O in M0.
        return [[(b / 127.5) - 1 for b in hashlib.sha256(t.encode()).digest()[:8]] for t in texts]


class Retrieval:
    def __init__(self, client: AsyncQdrantClient):
        self.client = client

    async def search(self, workspace_id: UUID, snapshot_id: UUID, vector: list[float]):
        return await self.client.query_points(
            collection_name="fixture_v1",
            query=vector,
            limit=5,
            query_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="workspace_id", match=models.MatchValue(value=str(workspace_id))
                    ),
                    models.FieldCondition(
                        key="snapshot_id", match=models.MatchValue(value=str(snapshot_id))
                    ),
                ]
            ),
            with_payload=True,
        )
