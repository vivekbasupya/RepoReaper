import asyncio
from uuid import UUID, uuid5

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from qdrant_client import AsyncQdrantClient, models
from sqlalchemy import text

from reporeaper.adapters import FixtureEmbedding
from reporeaper.config import Settings
from reporeaper.db import Database, encode
from reporeaper.fixtures import CATALOG, manifest
from reporeaper.languages import detect

USER = UUID("00000000-0000-4000-8000-000000000001")
WORKSPACE = UUID("00000000-0000-4000-8000-000000000002")
OTHER_WORKSPACE = UUID("00000000-0000-4000-8000-000000000003")


async def seed():
    settings = Settings()
    db = Database(settings)
    # Saver owns its schema; deployment-only setup, never per API startup.
    async with AsyncPostgresSaver.from_conn_string(settings.checkpoint_url) as saver:
        await saver.setup()
    q = AsyncQdrantClient(url=settings.qdrant_url, timeout=5)
    if not await q.collection_exists("fixture_v1"):
        await q.create_collection(
            "fixture_v1",
            vectors_config=models.VectorParams(size=8, distance=models.Distance.COSINE),
        )
        for field in ("workspace_id", "snapshot_id"):
            await q.create_payload_index("fixture_v1", field, models.PayloadSchemaType.KEYWORD)
    try:
        async with db.transaction() as c:
            await c.execute(
                text("INSERT INTO users VALUES(:id,'Local developer') ON CONFLICT DO NOTHING"),
                {"id": USER},
            )
            for workspace in (WORKSPACE, OTHER_WORKSPACE):
                await c.execute(
                    text("INSERT INTO workspaces VALUES(:id,:name) ON CONFLICT DO NOTHING"),
                    {
                        "id": workspace,
                        "name": "Local lab" if workspace == WORKSPACE else "Isolation fixture",
                    },
                )
                if workspace == WORKSPACE:
                    await c.execute(
                        text(
                            "INSERT INTO memberships VALUES(:w,:u,'owner') ON CONFLICT DO NOTHING"
                        ),
                        {"w": workspace, "u": USER},
                    )
                for fixture in CATALOG:
                    repo = uuid5(workspace, fixture)
                    data = manifest(fixture)
                    snapshot = uuid5(repo, data["base_sha"])
                    await c.execute(
                        text("""INSERT INTO repositories VALUES(:id,:w,:name,:fixture)
                        ON CONFLICT DO NOTHING"""),
                        dict(id=repo, w=workspace, name=fixture, fixture=fixture),
                    )
                    await c.execute(
                        text("""INSERT INTO snapshots VALUES(:id,:w,:repo,:sha,CAST(:data AS jsonb))
                        ON CONFLICT DO NOTHING"""),
                        dict(
                            id=snapshot,
                            w=workspace,
                            repo=repo,
                            sha=data["base_sha"],
                            data=encode(data),
                        ),
                    )
                    points = []
                    for path, source in data["files"].items():
                        adapter = detect(path)
                        payload = {
                            "workspace_id": str(workspace),
                            "snapshot_id": str(snapshot),
                            "path": path,
                            "commit_sha": data["base_sha"],
                            "language": adapter.name if adapter else "text_fallback",
                            "symbols": adapter.symbols(source.encode()) if adapter else [],
                            "text": source[:4000],
                            "embedding": "fixture-hash-v1 (nonsemantic)",
                        }
                        vector = (await FixtureEmbedding().embed([source]))[0]
                        points.append(
                            models.PointStruct(
                                id=str(uuid5(snapshot, path)), vector=vector, payload=payload
                            )
                        )
                    await q.upsert("fixture_v1", points=points, wait=True)
        print("Seeded workspace-scoped immutable fixtures and real Qdrant points")
    finally:
        await q.close()
        await db.close()


if __name__ == "__main__":
    asyncio.run(seed())
