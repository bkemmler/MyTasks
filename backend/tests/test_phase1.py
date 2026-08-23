from __future__ import annotations

from httpx import AsyncClient


class TestAuth:
    async def test_login_success(self, client: AsyncClient):
        from app.core.database import async_session_factory
        from app.core.security import hash_password
        from app.models.user import User

        async with async_session_factory() as db:
            user = User(
                username="testuser",
                password_hash=hash_password("testusertestuser"),
                is_active=True,
            )
            db.add(user)
            await db.commit()

        resp = await client.post(
            "/api/v1/auth/login",
            json={"username": "testuser", "password": "testusertestuser"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    async def test_login_invalid_password(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/auth/login",
            json={"username": "nonexistent", "password": "wrongwrongwrong"},
        )
        assert resp.status_code == 401

    async def test_refresh_token(self, client: AsyncClient):
        from app.core.database import async_session_factory
        from app.core.security import hash_password
        from app.models.user import User

        async with async_session_factory() as db:
            user = User(
                username="refreshuser",
                password_hash=hash_password("refreshrefreshr"),
                is_active=True,
            )
            db.add(user)
            await db.commit()

        login_resp = await client.post(
            "/api/v1/auth/login",
            json={"username": "refreshuser", "password": "refreshrefreshr"},
        )
        refresh_token = login_resp.json()["refresh_token"]

        resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data

    async def test_invalid_refresh_token(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": "invalid-token-string-here"},
        )
        assert resp.status_code == 401

    async def test_me_endpoint(self, auth_client: AsyncClient):
        resp = await auth_client.get("/api/v1/auth/me")
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "admin"
        assert data["is_admin"] is True

    async def test_me_unauthorized(self, client: AsyncClient):
        resp = await client.get("/api/v1/auth/me")
        assert resp.status_code == 401

    async def test_change_password(self, auth_client: AsyncClient):
        resp = await auth_client.post(
            "/api/v1/auth/me/password",
            json={
                "old_password": "adminadminadmin",
                "new_password": "newpassword12345678",
            },
        )
        assert resp.status_code == 200

        resp = await auth_client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "newpassword12345678"},
        )
        assert resp.status_code == 200

    async def test_change_password_wrong_old(self, auth_client: AsyncClient):
        resp = await auth_client.post(
            "/api/v1/auth/me/password",
            json={
                "old_password": "wrongpassword99999",
                "new_password": "newpassword12345678",
            },
        )
        assert resp.status_code == 401

    async def test_logout(self, client: AsyncClient):
        from app.core.database import async_session_factory
        from app.core.security import hash_password
        from app.models.user import User

        async with async_session_factory() as db:
            user = User(
                username="logoutuser",
                password_hash=hash_password("logoutlogoutlog"),
                is_active=True,
            )
            db.add(user)
            await db.commit()

        login_resp = await client.post(
            "/api/v1/auth/login",
            json={"username": "logoutuser", "password": "logoutlogoutlog"},
        )
        refresh_token = login_resp.json()["refresh_token"]

        resp = await client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": refresh_token},
        )
        assert resp.status_code == 200

        resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert resp.status_code == 401


class TestAdmin:
    async def test_create_user(self, auth_client: AsyncClient):
        resp = await auth_client.post(
            "/api/v1/admin/users",
            json={
                "username": "newuser",
                "password": "newuserpassword12",
                "display_name": "New User",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["username"] == "newuser"
        assert data["must_change_password"] is True

    async def test_list_users(self, auth_client: AsyncClient):
        resp = await auth_client.get("/api/v1/admin/users")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1

    async def test_get_user(self, auth_client: AsyncClient):
        resp = await auth_client.get("/api/v1/admin/users/1")
        assert resp.status_code == 200

    async def test_update_user(self, auth_client: AsyncClient):
        resp = await auth_client.patch(
            "/api/v1/admin/users/1",
            json={"display_name": "Updated Admin"},
        )
        assert resp.status_code == 200
        assert resp.json()["display_name"] == "Updated Admin"

    async def test_reset_password(self, auth_client: AsyncClient):
        resp = await auth_client.post(
            "/api/v1/admin/users/1/reset-password",
            json={"new_password": "resetpassword12345"},
        )
        assert resp.status_code == 200

    async def test_soft_delete_user(self, auth_client: AsyncClient):
        resp = await auth_client.delete("/api/v1/admin/users/1")
        assert resp.status_code == 204

    async def test_admin_access_denied_for_non_admin(self, user_client: AsyncClient):
        resp = await user_client.get("/api/v1/admin/users")
        assert resp.status_code == 401

    async def test_create_duplicate_user(self, auth_client: AsyncClient):
        await auth_client.post(
            "/api/v1/admin/users",
            json={"username": "dupuser", "password": "duplicatepassword1"},
        )
        resp = await auth_client.post(
            "/api/v1/admin/users",
            json={"username": "dupuser", "password": "anotherpassword1"},
        )
        assert resp.status_code == 409


class TestTasks:
    async def test_create_task(self, auth_client: AsyncClient):
        resp = await auth_client.post(
            "/api/v1/tasks",
            json={"title": "Test Task"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "Test Task"
        assert "uuid" in data
        assert data["status"] == "offen"
        assert data["priority"] == 3

    async def test_list_tasks(self, auth_client: AsyncClient):
        await auth_client.post("/api/v1/tasks", json={"title": "Task 1"})
        await auth_client.post("/api/v1/tasks", json={"title": "Task 2"})

        resp = await auth_client.get("/api/v1/tasks")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

    async def test_get_task_by_uuid(self, auth_client: AsyncClient):
        create_resp = await auth_client.post(
            "/api/v1/tasks", json={"title": "Get Me"}
        )
        uuid = create_resp.json()["uuid"]

        resp = await auth_client.get(f"/api/v1/tasks/{uuid}")
        assert resp.status_code == 200
        assert resp.json()["title"] == "Get Me"

    async def test_get_task_not_found(self, auth_client: AsyncClient):
        resp = await auth_client.get("/api/v1/tasks/nonexistent-uuid")
        assert resp.status_code == 404

    async def test_update_task(self, auth_client: AsyncClient):
        create_resp = await auth_client.post(
            "/api/v1/tasks", json={"title": "Original Title"}
        )
        uuid = create_resp.json()["uuid"]

        resp = await auth_client.patch(
            f"/api/v1/tasks/{uuid}",
            json={"title": "Updated Title", "priority": 1},
        )
        assert resp.status_code == 200
        assert resp.json()["title"] == "Updated Title"
        assert resp.json()["priority"] == 1

    async def test_clear_due_at_with_null(self, auth_client: AsyncClient):
        """Explizites due_at: null muss das Datum löschen (nicht ignorieren)."""
        create_resp = await auth_client.post(
            "/api/v1/tasks",
            json={"title": "Mit Datum", "due_at": "2026-08-15T10:00:00"},
        )
        uuid = create_resp.json()["uuid"]
        assert create_resp.json()["due_at"] is not None

        resp = await auth_client.patch(
            f"/api/v1/tasks/{uuid}", json={"due_at": None}
        )
        assert resp.status_code == 200
        assert resp.json()["due_at"] is None

    async def test_date_only_due_at(self, auth_client: AsyncClient):
        """Datum ohne Uhrzeit (Mitternacht) muss gespeichert werden."""
        create_resp = await auth_client.post(
            "/api/v1/tasks", json={"title": "Nur Datum"}
        )
        uuid = create_resp.json()["uuid"]

        resp = await auth_client.patch(
            f"/api/v1/tasks/{uuid}",
            json={"due_at": "2026-08-15T00:00:00"},
        )
        assert resp.status_code == 200
        assert resp.json()["due_at"] is not None
        assert resp.json()["due_at"].startswith("2026-08-15T00:00")

    async def test_clear_waiting_for(self, auth_client: AsyncClient):
        create_resp = await auth_client.post(
            "/api/v1/tasks",
            json={"title": "Wartend", "status": "wartend", "waiting_for": "Sabine"},
        )
        uuid = create_resp.json()["uuid"]

        resp = await auth_client.patch(
            f"/api/v1/tasks/{uuid}", json={"waiting_for": None}
        )
        assert resp.status_code == 200
        assert resp.json()["waiting_for"] is None

    async def test_complete_task(self, auth_client: AsyncClient):
        create_resp = await auth_client.post(
            "/api/v1/tasks", json={"title": "Complete Me"}
        )
        uuid = create_resp.json()["uuid"]

        resp = await auth_client.post(f"/api/v1/tasks/{uuid}/complete")
        assert resp.status_code == 200
        assert resp.json()["status"] == "erledigt"

    async def test_soft_delete_task(self, auth_client: AsyncClient):
        create_resp = await auth_client.post(
            "/api/v1/tasks", json={"title": "Delete Me"}
        )
        uuid = create_resp.json()["uuid"]

        resp = await auth_client.delete(f"/api/v1/tasks/{uuid}")
        assert resp.status_code == 204

        resp = await auth_client.get(f"/api/v1/tasks/{uuid}")
        assert resp.status_code == 404

    async def test_capture_task(self, auth_client: AsyncClient):
        resp = await auth_client.post(
            "/api/v1/tasks/capture",
            json={"text": "Angebot Fa. Müller bis Freitag fertigstellen"},
        )
        assert resp.status_code == 201
        data = resp.json()
        tasks = data if isinstance(data, list) else [data]
        assert len(tasks) >= 1
        assert tasks[0]["source_text"] == "Angebot Fa. Müller bis Freitag fertigstellen"
        assert tasks[0]["llm_state"] == "pending"

    async def test_task_filter_by_status(self, auth_client: AsyncClient):
        await auth_client.post(
            "/api/v1/tasks",
            json={"title": "Open Task", "status": "offen"},
        )
        await auth_client.post(
            "/api/v1/tasks",
            json={"title": "In Progress", "status": "in_bearbeitung"},
        )

        resp = await auth_client.get("/api/v1/tasks?status=offen")
        assert resp.status_code == 200
        tasks = resp.json()
        assert all(t["status"] == "offen" for t in tasks)

    async def test_subtask_crud(self, auth_client: AsyncClient):
        create_resp = await auth_client.post(
            "/api/v1/tasks", json={"title": "Task with subtasks"}
        )
        uuid = create_resp.json()["uuid"]

        st_resp = await auth_client.post(
            f"/api/v1/tasks/{uuid}/subtasks",
            json={"title": "Subtask 1"},
        )
        assert st_resp.status_code == 201
        subtask_id = st_resp.json()["id"]
        assert st_resp.json()["title"] == "Subtask 1"

        toggle_resp = await auth_client.post(
            f"/api/v1/tasks/{uuid}/subtasks/{subtask_id}/toggle"
        )
        assert toggle_resp.status_code == 200
        assert toggle_resp.json()["is_done"] is True

        del_resp = await auth_client.delete(
            f"/api/v1/tasks/{uuid}/subtasks/{subtask_id}"
        )
        assert del_resp.status_code == 204


class TestCategories:
    async def test_create_category(self, auth_client: AsyncClient):
        resp = await auth_client.post(
            "/api/v1/categories",
            json={"name": "Arbeit", "color": "#ff0000"},
        )
        assert resp.status_code == 201
        assert resp.json()["name"] == "Arbeit"

    async def test_list_categories(self, auth_client: AsyncClient):
        await auth_client.post(
            "/api/v1/categories", json={"name": "Privat"}
        )
        resp = await auth_client.get("/api/v1/categories")
        assert resp.status_code == 200
        assert any(c["name"] == "Privat" for c in resp.json())

    async def test_update_category(self, auth_client: AsyncClient):
        create_resp = await auth_client.post(
            "/api/v1/categories", json={"name": "UpdateMe"}
        )
        cat_id = create_resp.json()["id"]

        resp = await auth_client.patch(
            f"/api/v1/categories/{cat_id}",
            json={"color": "#00ff00"},
        )
        assert resp.status_code == 200
        assert resp.json()["color"] == "#00ff00"

    async def test_delete_category(self, auth_client: AsyncClient):
        create_resp = await auth_client.post(
            "/api/v1/categories", json={"name": "DeleteMe"}
        )
        cat_id = create_resp.json()["id"]

        resp = await auth_client.delete(f"/api/v1/categories/{cat_id}")
        assert resp.status_code == 204


class TestTags:
    async def test_list_tags(self, auth_client: AsyncClient):
        resp = await auth_client.get("/api/v1/tags")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


class TestSearch:
    async def test_search_tasks(self, auth_client: AsyncClient):
        await auth_client.post(
            "/api/v1/tasks",
            json={"title": "Angebot Test erstellung", "description": "Dringend"},
        )
        await auth_client.post(
            "/api/v1/tasks", json={"title": "Rechnung prüfen"}
        )

        resp = await auth_client.get("/api/v1/tasks/search?q=Test")
        assert resp.status_code == 200
        results = resp.json()
        assert len(results) >= 1
        assert any("Test" in t["title"] for t in results)

    async def test_search_no_results(self, auth_client: AsyncClient):
        resp = await auth_client.get("/api/v1/tasks/search?q=nonexistentxyz")
        assert resp.status_code == 200
        assert resp.json() == []


class TestIsolation:
    async def test_user_cannot_access_other_users_tasks(
        self, auth_client: AsyncClient, client: AsyncClient
    ):
        """Nutzer B darf nicht auf Tasks von Nutzer A zugreifen (sollte 404)."""
        create_resp = await auth_client.post(
            "/api/v1/tasks", json={"title": "Admin Task"}
        )
        admin_uuid = create_resp.json()["uuid"]

        resp = await client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "adminadminadmin"},
        )
        _ = resp.json()["access_token"]

        from app.core.database import async_session_factory
        from app.core.security import hash_password
        from app.models.user import User

        async with async_session_factory() as db:
            user = User(
                username="other",
                password_hash=hash_password("otherotherother"),
                is_active=True,
            )
            db.add(user)
            await db.commit()

        resp = await client.post(
            "/api/v1/auth/login",
            json={"username": "other", "password": "otherotherother"},
        )
        other_token = resp.json()["access_token"]

        client.headers["Authorization"] = f"Bearer {other_token}"
        resp = await client.get(f"/api/v1/tasks/{admin_uuid}")
        assert resp.status_code == 404

    async def test_user_cannot_update_other_users_task(
        self, auth_client: AsyncClient, client: AsyncClient
    ):
        from app.core.database import async_session_factory
        from app.core.security import hash_password
        from app.models.user import User

        create_resp = await auth_client.post(
            "/api/v1/tasks", json={"title": "Admin Task 2"}
        )
        admin_uuid = create_resp.json()["uuid"]

        async with async_session_factory() as db:
            user = User(
                username="other2",
                password_hash=hash_password("other2other2ot"),
                is_active=True,
            )
            db.add(user)
            await db.commit()

        resp = await client.post(
            "/api/v1/auth/login",
            json={"username": "other2", "password": "other2other2ot"},
        )
        other_token = resp.json()["access_token"]

        client.headers["Authorization"] = f"Bearer {other_token}"
        resp = await client.patch(
            f"/api/v1/tasks/{admin_uuid}",
            json={"title": "Hacked Title"},
        )
        assert resp.status_code == 404

    async def test_user_cannot_delete_other_users_task(
        self, auth_client: AsyncClient, client: AsyncClient
    ):
        from app.core.database import async_session_factory
        from app.core.security import hash_password
        from app.models.user import User

        create_resp = await auth_client.post(
            "/api/v1/tasks", json={"title": "Admin Task 3"}
        )
        admin_uuid = create_resp.json()["uuid"]

        async with async_session_factory() as db:
            user = User(
                username="other3",
                password_hash=hash_password("other3other3ot"),
                is_active=True,
            )
            db.add(user)
            await db.commit()

        resp = await client.post(
            "/api/v1/auth/login",
            json={"username": "other3", "password": "other3other3ot"},
        )
        other_token = resp.json()["access_token"]

        client.headers["Authorization"] = f"Bearer {other_token}"
        resp = await client.delete(f"/api/v1/tasks/{admin_uuid}")
        assert resp.status_code == 404

    async def test_user_cannot_access_other_users_categories(
        self, auth_client: AsyncClient, client: AsyncClient
    ):
        from app.core.database import async_session_factory
        from app.core.security import hash_password
        from app.models.user import User

        create_resp = await auth_client.post(
            "/api/v1/categories", json={"name": "Admin Category"}
        )
        admin_cat_id = create_resp.json()["id"]

        async with async_session_factory() as db:
            user = User(
                username="other4",
                password_hash=hash_password("other4other4ot"),
                is_active=True,
            )
            db.add(user)
            await db.commit()

        resp = await client.post(
            "/api/v1/auth/login",
            json={"username": "other4", "password": "other4other4ot"},
        )
        other_token = resp.json()["access_token"]

        client.headers["Authorization"] = f"Bearer {other_token}"
        resp = await client.get("/api/v1/categories")
        cats = resp.json()
        assert not any(c["id"] == admin_cat_id for c in cats)

        resp = await client.patch(
            f"/api/v1/categories/{admin_cat_id}",
            json={"name": "Hacked Category"},
        )
        assert resp.status_code == 404


class TestPhase2:
    async def test_capture_creates_job(self, auth_client: AsyncClient):
        resp = await auth_client.post(
            "/api/v1/tasks/capture",
            json={"text": "Test Capture mit LLM Job"},
        )
        assert resp.status_code == 201
        tasks = resp.json()
        assert isinstance(tasks, list)
        assert tasks[0]["llm_state"] == "pending"

        from sqlalchemy import select

        from app.core.database import async_session_factory
        from app.models.llm import LLMJob

        async with async_session_factory() as db:
            result = await db.execute(
                select(LLMJob).where(LLMJob.job_type == "capture")
            )
            jobs = result.scalars().all()
            assert len(jobs) >= 1
            assert jobs[0].state == "queued"

    async def test_confirm_review(self, auth_client: AsyncClient):
        resp = await auth_client.post(
            "/api/v1/tasks",
            json={"title": "Task needs review"},
        )
        uuid = resp.json()["uuid"]

        from sqlalchemy import select

        from app.core.database import async_session_factory
        from app.models.task import Task

        async with async_session_factory() as db:
            result = await db.execute(select(Task).where(Task.uuid == uuid))
            task = result.scalar_one()
            task.needs_review = True
            await db.commit()

        resp = await auth_client.post(f"/api/v1/tasks/{uuid}/confirm-review")
        assert resp.status_code == 200
        assert resp.json()["needs_review"] is False

    async def test_reparse_creates_job(self, auth_client: AsyncClient):
        resp = await auth_client.post(
            "/api/v1/tasks/capture",
            json={"text": "Angebot Müller bis Freitag fertigstellen"},
        )
        uuid = resp.json()[0]["uuid"]
        resp = await auth_client.post(f"/api/v1/tasks/{uuid}/reparse")
        assert resp.status_code == 200
        assert resp.json()["llm_state"] == "pending"

    async def test_reparse_no_source_text(self, auth_client: AsyncClient):
        resp = await auth_client.post(
            "/api/v1/tasks",
            json={"title": "Task ohne source_text"},
        )
        uuid = resp.json()["uuid"]
        resp = await auth_client.post(f"/api/v1/tasks/{uuid}/reparse")
        assert resp.status_code == 422

    async def test_health_includes_ollama(self, client: AsyncClient):
        resp = await client.get("/api/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "ollama" in data
