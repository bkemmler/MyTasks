"""Tests für die pro-Nutzer-Mail-Konfiguration (Phase 7)."""
from __future__ import annotations

import pytest
from httpx import AsyncClient

CONFIG = {
    "smtp_host": "mail.example.de",
    "smtp_port": 587,
    "smtp_security": "starttls",
    "smtp_username": "bernd",
    "smtp_password": "geheim123456",
    "from_address": "bernd@example.de",
    "from_name": "Bernd",
}


@pytest.mark.anyio
class TestMailConfigCrud:
    async def test_get_without_config_returns_404(self, auth_client: AsyncClient):
        resp = await auth_client.get("/api/v1/auth/me/mail-config")
        assert resp.status_code == 404

    async def test_put_and_get(self, auth_client: AsyncClient):
        resp = await auth_client.put("/api/v1/auth/me/mail-config", json=CONFIG)
        assert resp.status_code == 200
        data = resp.json()
        assert data["smtp_host"] == "mail.example.de"
        assert data["has_password"] is True
        # Passwort darf nie im Response stehen
        assert "smtp_password" not in data
        assert "geheim" not in resp.text

        resp = await auth_client.get("/api/v1/auth/me/mail-config")
        assert resp.status_code == 200
        assert resp.json()["smtp_host"] == "mail.example.de"
        assert "geheim" not in resp.text

    async def test_update_keeps_password_when_empty(self, auth_client: AsyncClient):
        await auth_client.put("/api/v1/auth/me/mail-config", json=CONFIG)
        updated = {**CONFIG, "smtp_password": None, "smtp_host": "other.example.de"}
        resp = await auth_client.put("/api/v1/auth/me/mail-config", json=updated)
        assert resp.status_code == 200
        assert resp.json()["smtp_host"] == "other.example.de"
        assert resp.json()["has_password"] is True  # altes Passwort bleibt

    async def test_invalid_security_rejected(self, auth_client: AsyncClient):
        bad = {**CONFIG, "smtp_security": "quatsch"}
        resp = await auth_client.put("/api/v1/auth/me/mail-config", json=bad)
        assert resp.status_code == 422

    async def test_delete(self, auth_client: AsyncClient):
        await auth_client.put("/api/v1/auth/me/mail-config", json=CONFIG)
        resp = await auth_client.delete("/api/v1/auth/me/mail-config")
        assert resp.status_code == 204
        resp = await auth_client.get("/api/v1/auth/me/mail-config")
        assert resp.status_code == 404

    async def test_configs_are_user_isolated(
        self, client: AsyncClient, auth_client: AsyncClient
    ):
        """Nutzer B sieht die Mail-Konfiguration von Nutzer A nicht."""
        from tests.conftest import _create_user, _login

        await _create_user("bob", "bobpasswort123", is_admin=False)
        token_b = await _login(client, "bob", "bobpasswort123")

        resp = await auth_client.put("/api/v1/auth/me/mail-config", json=CONFIG)
        assert resp.status_code == 200

        old_auth = client.headers["Authorization"]
        client.headers["Authorization"] = f"Bearer {token_b}"
        resp = await client.get("/api/v1/auth/me/mail-config")
        assert resp.status_code == 404
        client.headers["Authorization"] = old_auth


@pytest.mark.anyio
class TestMailConfigTest:
    async def test_test_endpoint_without_config(self, auth_client: AsyncClient):
        resp = await auth_client.post("/api/v1/auth/me/mail-config/test", json={})
        assert resp.status_code == 200
        assert resp.json()["success"] is False

    async def test_test_endpoint_with_unreachable_server(self, auth_client: AsyncClient):
        """Unerreichbarer Server → success False, kein Crash."""
        bad = {**CONFIG, "smtp_host": "127.0.0.1", "smtp_port": 1}
        await auth_client.put("/api/v1/auth/me/mail-config", json=bad)
        resp = await auth_client.post("/api/v1/auth/me/mail-config/test", json={})
        assert resp.status_code == 200
        assert resp.json()["success"] is False


@pytest.mark.anyio
class TestPasswordEncryption:
    async def test_password_stored_encrypted(self, auth_client: AsyncClient):
        """Das Passwort liegt verschlüsselt in der DB, nicht im Klartext."""
        from sqlalchemy import text as sql_text

        from app.core.database import async_session_factory
        from app.services.user_mail import decrypt_password

        await auth_client.put("/api/v1/auth/me/mail-config", json=CONFIG)

        async with async_session_factory() as db:
            result = await db.execute(sql_text(
                "SELECT smtp_password_encrypted FROM user_mail_configs"
            ))
            stored = result.scalar()
        assert stored is not None
        assert "geheim" not in stored
        assert decrypt_password(stored) == "geheim123456"

    async def test_smtp_config_roundtrip(self, auth_client: AsyncClient):
        from sqlalchemy import select

        from app.core.database import async_session_factory
        from app.models.user import User
        from app.services.user_mail import get_smtp_config

        await auth_client.put("/api/v1/auth/me/mail-config", json=CONFIG)

        async with async_session_factory() as db:
            result = await db.execute(select(User).where(User.username == "admin"))
            user = result.scalar_one()
            cfg = await get_smtp_config(db, user)
        assert cfg is not None
        assert cfg.host == "mail.example.de"
        assert cfg.password == "geheim123456"
        assert cfg.from_address == "bernd@example.de"
        assert cfg.is_complete()

    async def test_no_config_means_no_smtp(self, auth_client: AsyncClient):
        """Ohne eigene Konfiguration: get_smtp_config → None (kein Fallback)."""
        from sqlalchemy import select

        from app.core.database import async_session_factory
        from app.models.user import User
        from app.services.user_mail import get_smtp_config

        async with async_session_factory() as db:
            result = await db.execute(select(User).where(User.username == "admin"))
            user = result.scalar_one()
            assert await get_smtp_config(db, user) is None
