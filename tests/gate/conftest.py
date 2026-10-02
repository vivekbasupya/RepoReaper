import os

import httpx
import pytest
from reporeaper.config import Settings
from reporeaper.db import Database


@pytest.fixture
async def db():
    database = Database(Settings())
    yield database
    await database.close()


@pytest.fixture
async def api():
    async with httpx.AsyncClient(
        base_url=os.environ.get("GATE_API_URL", "http://api:8000"), timeout=10
    ) as client:
        response = await client.get("/api/v1/session")
        response.raise_for_status()
        yield client


@pytest.fixture
async def runner():
    settings = Settings()
    async with httpx.AsyncClient(
        base_url=settings.runner_url,
        timeout=10,
        headers={"Authorization": f"Bearer {settings.runner_token}"},
    ) as client:
        yield client
