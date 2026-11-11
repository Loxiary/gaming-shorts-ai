from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def test_health_ok(client: TestClient) -> None:
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["worker"]["alive"] is False  # aucun worker lancé pendant ce test


def test_health_reports_unmigrated_db(settings: Settings) -> None:
    with TestClient(create_app(settings, configure_logs=False)) as c:
        body = c.get("/api/health").json()
        assert body["status"] == "degraded"
        assert body["database"] == "migration_required"
        r = c.get("/api/projects")
        assert r.status_code == 503
        assert r.json()["error"]["code"] == "database_not_ready"


def test_create_list_get_project(client: TestClient) -> None:
    r = client.post(
        "/api/projects",
        json={"name": "  GTA 6 — test  ", "game": "GTA 6", "description": "", "is_test": True},
    )
    assert r.status_code == 201
    created = r.json()
    assert created["name"] == "GTA 6 — test"
    assert created["description"] is None
    assert created["is_test"] is True
    assert created["created_at"].endswith("Z") or created["created_at"].endswith("+00:00")

    listed = client.get("/api/projects").json()
    assert [p["id"] for p in listed] == [created["id"]]
    assert listed[0]["job_counts"]["total"] == 0

    detail = client.get(f"/api/projects/{created['id']}").json()
    assert detail["jobs"] == []


def test_create_project_validation(client: TestClient) -> None:
    assert client.post("/api/projects", json={"name": "   "}).status_code == 422
    assert client.post("/api/projects", json={}).status_code == 422
    assert client.post("/api/projects", json={"name": "x" * 201}).status_code == 422
    assert client.post("/api/projects", json={"name": "ok", "inconnu": 1}).status_code == 422


def test_update_project(client: TestClient, project_id: str) -> None:
    r = client.patch(f"/api/projects/{project_id}", json={"name": "Renommé", "game": "GTA 6"})
    assert r.status_code == 200
    assert r.json()["name"] == "Renommé"
    assert r.json()["game"] == "GTA 6"
    assert client.patch(f"/api/projects/{project_id}", json={"name": ""}).status_code == 422


def test_not_found(client: TestClient) -> None:
    r = client.get("/api/projects/inexistant")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_delete_requires_confirmation(client: TestClient, project_id: str) -> None:
    r = client.delete(f"/api/projects/{project_id}")
    assert r.status_code == 400
    assert client.get(f"/api/projects/{project_id}").status_code == 200

    client.post("/api/jobs", json={"project_id": project_id, "kind": "demo"})
    assert client.delete(f"/api/projects/{project_id}?confirm=true").status_code == 204
    assert client.get(f"/api/projects/{project_id}").status_code == 404
    assert client.get("/api/jobs").json() == []  # cascade


def test_project_persists_across_app_restart(migrated: Settings) -> None:
    with TestClient(create_app(migrated, configure_logs=False)) as c:
        pid = c.post("/api/projects", json={"name": "Persistant"}).json()["id"]
    with TestClient(create_app(migrated, configure_logs=False)) as c:
        r = c.get(f"/api/projects/{pid}")
        assert r.status_code == 200
        assert r.json()["name"] == "Persistant"


def test_system_info(client: TestClient, migrated: Settings) -> None:
    body = client.get("/api/system").json()
    assert body["data_dir"] == str(migrated.data_dir)
    assert {d["name"] for d in body["data_dirs"]} == {
        "sources",
        "temp",
        "projects",
        "exports",
        "logs",
        "models",
        "music",
        "backups",
    }
    assert any(not f["available"] for f in body["features"])
    assert {t["name"] for t in body["tools"]} == {"ffmpeg", "ffprobe"}
