from __future__ import annotations

import os

os.environ["TASKS_RATE_LIMIT_ENABLED"] = "false"

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.core.database import Base, async_session_factory, engine
from app.core.security import hash_password
from app.main import app
from app.models.user import User


@pytest.fixture(autouse=True)
async def _setup_db():
    from pathlib import Path

    db_path = Path("var/tasks.db")
    db_path.parent.mkdir(parents=True, exist_ok=True)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    from app.core.database import _create_fts
    async with engine.begin() as conn:
        await _create_fts(conn)
        await conn.execute(text("PRAGMA journal_mode=WAL"))
        await conn.execute(text("PRAGMA foreign_keys=ON"))

    yield

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _create_user(
    username: str = "admin",
    password: str = "adminadminadmin",
    is_admin: bool = True,
) -> tuple[User, str]:
    async with async_session_factory() as db:
        user = User(
            username=username,
            password_hash=hash_password(password),
            is_admin=is_admin,
            is_active=True,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user, password


async def _login(client: AsyncClient, username: str, password: str) -> str:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture
async def auth_client(client: AsyncClient) -> AsyncClient:
    username = "admin"
    password = "adminadminadmin"
    await _create_user(username, password, is_admin=True)
    token = await _login(client, username, password)
    client.headers["Authorization"] = f"Bearer {token}"
    return client


@pytest.fixture
async def user_client(client: AsyncClient) -> AsyncClient:
    username = "user1"
    password = "user1user1user1"
    await _create_user(username, password, is_admin=False)
    token = await _login(client, username, password)
    client.headers["Authorization"] = f"Bearer {token}"
    return client
