from __future__ import annotations

from httpx import AsyncClient


class TestReports:
    async def test_export_json(self, auth_client: AsyncClient):
        await auth_client.post("/api/v1/tasks", json={"title": "Export Test 1"})

        resp = await auth_client.get("/api/v1/reports/export?format=json")
        assert resp.status_code == 200
        data = resp.json()
        assert "exported_at" in data
        assert "tasks" in data
        assert any(t["title"] == "Export Test 1" for t in data["tasks"])

    async def test_export_csv(self, auth_client: AsyncClient):
        await auth_client.post("/api/v1/tasks", json={"title": "CSV Test"})

        resp = await auth_client.get("/api/v1/reports/export?format=csv")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]
        assert "title" in resp.text
        assert "CSV Test" in resp.text

    async def test_stats(self, auth_client: AsyncClient):
        for i in range(3):
            await auth_client.post("/api/v1/tasks", json={"title": f"Task {i}"})

        resp = await auth_client.get("/api/v1/reports/stats?days=30")
        assert resp.status_code == 200
        data = resp.json()
        assert data["period_days"] == 30
        assert data["created"] >= 3
        assert "open_by_priority" in data
        assert "avg_completion_hours" in data

    async def test_export_unauthorized(self, client: AsyncClient):
        resp = await client.get("/api/v1/reports/export")
        assert resp.status_code == 401


class TestRecurrence:
    async def test_complete_recurring_creates_next(self, auth_client: AsyncClient):
        create = await auth_client.post(
            "/api/v1/tasks",
            json={
                "title": "Wöchentlicher Report",
                "recurrence_rule": "FREQ=WEEKLY",
                "due_at": "2026-08-09T10:00:00",
            },
        )
        first_uuid = create.json()["uuid"]

        resp = await auth_client.post(f"/api/v1/tasks/{first_uuid}/complete")
        assert resp.status_code == 200
        assert resp.json()["status"] == "erledigt"

        # Liste zeigt jetzt 2 Tasks: erledigt + neu (offen)
        resp = await auth_client.get("/api/v1/tasks?include_completed=true")
        tasks = resp.json()
        recurred = [t for t in tasks if t["title"] == "Wöchentlicher Report"]
        assert len(recurred) == 2
        completed = [t for t in recurred if t["status"] == "erledigt"]
        open_ones = [t for t in recurred if t["status"] == "offen"]
        assert len(completed) == 1
        assert len(open_ones) == 1

    async def test_non_recurring_no_next(self, auth_client: AsyncClient):
        create = await auth_client.post(
            "/api/v1/tasks", json={"title": "Einmalig"}
        )
        uuid = create.json()["uuid"]
        await auth_client.post(f"/api/v1/tasks/{uuid}/complete")

        resp = await auth_client.get("/api/v1/tasks?include_completed=true")
        titles = [t["title"] for t in resp.json()]
        assert titles.count("Einmalig") == 1


class TestSummaryPreview:
    async def test_summary_preview(self, auth_client: AsyncClient):
        await auth_client.post(
            "/api/v1/tasks",
            json={"title": "Morgen fällig", "due_at": "2026-08-10T09:00:00"},
        )
        resp = await auth_client.post("/api/v1/admin/summary/preview")
        assert resp.status_code == 200
        data = resp.json()
        assert "sections" in data
        assert "html" in data
        assert "text" in data
        assert "MyTasks" in data["html"] or "Heute" in data["html"]


class TestSmtp:
    async def test_smtp_test_without_config(self, auth_client: AsyncClient):
        resp = await auth_client.post(
            "/api/v1/admin/smtp/test",
            json={"to_address": "test@example.com"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
