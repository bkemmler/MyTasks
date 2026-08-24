"""Tests für die pro-Nutzer-LLM-Konfiguration."""
from __future__ import annotations

import pytest
from httpx import AsyncClient

CONFIG = {
    "ollama_base_url": "http://192.168.100.91:11434",
    "ollama_model": "gemma4:e2b",
}


@pytest.mark.anyio
class TestLLMConfigCrud:
    async def test_get_without_config_returns_404(self, auth_client: AsyncClient):
        resp = await auth_client.get("/api/v1/auth/me/llm-config")
        assert resp.status_code == 404

    async def test_put_and_get(self, auth_client: AsyncClient):
        resp = await auth_client.put("/api/v1/auth/me/llm-config", json=CONFIG)
        assert resp.status_code == 200
        data = resp.json()
        assert data["ollama_base_url"] == "http://192.168.100.91:11434"
        assert data["ollama_model"] == "gemma4:e2b"
        assert data["enabled"] is True

    async def test_put_empty_model_disables(self, auth_client: AsyncClient):
        resp = await auth_client.put(
            "/api/v1/auth/me/llm-config",
            json={"ollama_base_url": "http://x:11434", "ollama_model": ""},
        )
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False

    async def test_invalid_base_url_rejected(self, auth_client: AsyncClient):
        resp = await auth_client.put(
            "/api/v1/auth/me/llm-config",
            json={"ollama_base_url": "ftp://quatsch", "ollama_model": "m"},
        )
        assert resp.status_code in (400, 422)

    async def test_delete(self, auth_client: AsyncClient):
        await auth_client.put("/api/v1/auth/me/llm-config", json=CONFIG)
        resp = await auth_client.delete("/api/v1/auth/me/llm-config")
        assert resp.status_code == 204
        resp = await auth_client.get("/api/v1/auth/me/llm-config")
        assert resp.status_code == 404

    async def test_configs_are_user_isolated(self, client: AsyncClient, auth_client: AsyncClient):
        from tests.conftest import _create_user, _login

        await _create_user("bob", "bobpasswort123", is_admin=False)
        token_b = await _login(client, "bob", "bobpasswort123")

        await auth_client.put("/api/v1/auth/me/llm-config", json=CONFIG)

        old_auth = client.headers["Authorization"]
        client.headers["Authorization"] = f"Bearer {token_b}"
        resp = await client.get("/api/v1/auth/me/llm-config")
        assert resp.status_code == 404
        client.headers["Authorization"] = old_auth


@pytest.mark.anyio
class TestLLMConfigTestEndpoint:
    async def test_test_without_any_config(self, auth_client: AsyncClient):
        resp = await auth_client.post("/api/v1/auth/me/llm-config/test", json={})
        assert resp.status_code == 200
        assert resp.json()["success"] is False

    async def test_test_unreachable_server(self, auth_client: AsyncClient):
        await auth_client.put(
            "/api/v1/auth/me/llm-config",
            json={"ollama_base_url": "http://127.0.0.1:1", "ollama_model": "x"},
        )
        resp = await auth_client.post("/api/v1/auth/me/llm-config/test", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False


@pytest.mark.anyio
class TestPipelineWithoutConfig:
    async def test_capture_works_without_llm_config(self, auth_client: AsyncClient):
        """Capture läuft rein lokal durch, wenn keine LLM-Config existiert."""
        from app.services.local_extract import local_extract

        r = local_extract("Müller anrufen morgen um 8")
        assert r["due_at"].startswith(str(__import__("datetime").date.today().year))
