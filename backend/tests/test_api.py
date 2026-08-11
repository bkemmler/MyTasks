from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_health(client: AsyncClient):
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert "uptime_seconds" in data


async def test_version(client: AsyncClient):
    response = await client.get("/api/v1/version")
    assert response.status_code == 200
    data = response.json()
    assert "app" in data
    assert "api" in data
    assert "db_schema" in data
    assert "git_sha" in data
    assert "built_at" in data
    assert "min_android" in data
