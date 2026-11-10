from __future__ import annotations

from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from app.core.time import utcnow
from app.models import Job, JobStep
from app.services.queue import claim_next_job, recover_stale_jobs
from app.workers.runner import Worker


def _job(client: TestClient, job_id: str) -> dict:
    return client.get(f"/api/jobs/{job_id}").json()


def test_job_kinds_are_demo_only(client: TestClient) -> None:
    kinds = client.get("/api/job-kinds").json()
    assert {k["kind"] for k in kinds} == {"demo", "demo_failure"}
    assert all(k["is_demo"] for k in kinds)


def test_enqueue_creates_persisted_steps(client: TestClient, project_id: str) -> None:
    r = client.post("/api/jobs", json={"project_id": project_id, "kind": "demo"})
    assert r.status_code == 201
    job = r.json()
    assert job["status"] == "queued"
    assert job["is_demo"] is True
    assert [s["status"] for s in job["steps"]] == ["pending"] * 4
    assert client.get(f"/api/jobs?project_id={project_id}").json()[0]["id"] == job["id"]


def test_enqueue_validation(client: TestClient, project_id: str) -> None:
    r = client.post("/api/jobs", json={"project_id": project_id, "kind": "youtube"})
    assert r.status_code == 400
    r = client.post("/api/jobs", json={"project_id": "absent", "kind": "demo"})
    assert r.status_code == 404


def test_duplicate_active_job_rejected(client: TestClient, project_id: str) -> None:
    assert (
        client.post("/api/jobs", json={"project_id": project_id, "kind": "demo"}).status_code == 201
    )
    r = client.post("/api/jobs", json={"project_id": project_id, "kind": "demo"})
    assert r.status_code == 409
    # Un autre type reste autorisé.
    r = client.post("/api/jobs", json={"project_id": project_id, "kind": "demo_failure"})
    assert r.status_code == 201


def test_worker_completes_demo_job(client: TestClient, project_id: str, worker: Worker) -> None:
    job_id = client.post("/api/jobs", json={"project_id": project_id, "kind": "demo"}).json()["id"]
    assert worker.run_once() is True
    job = _job(client, job_id)
    assert job["status"] == "completed"
    assert job["progress"] == 1.0
    assert job["attempts"] == 1
    assert job["finished_at"] is not None
    assert all(s["status"] == "completed" for s in job["steps"])
    assert worker.run_once() is False  # file vide
    assert client.get("/api/health").json()["worker"]["alive"] is True


def test_jobs_processed_sequentially_in_order(client: TestClient, worker: Worker) -> None:
    ids = []
    for name in ("A", "B"):
        pid = client.post("/api/projects", json={"name": name}).json()["id"]
        ids.append(client.post("/api/jobs", json={"project_id": pid, "kind": "demo"}).json()["id"])
    worker.run_once()
    assert _job(client, ids[0])["status"] == "completed"
    assert _job(client, ids[1])["status"] == "queued"


def test_failure_then_retry_resumes_from_failed_step(
    client: TestClient, project_id: str, worker: Worker
) -> None:
    job_id = client.post(
        "/api/jobs", json={"project_id": project_id, "kind": "demo_failure"}
    ).json()["id"]
    worker.run_once()
    job = _job(client, job_id)
    assert job["status"] == "failed"
    assert "Échec simulé" in job["error_message"]
    assert [s["status"] for s in job["steps"]] == ["completed", "completed", "failed", "pending"]
    first_done = job["steps"][0]["finished_at"]

    r = client.post(f"/api/jobs/{job_id}/retry")
    assert r.status_code == 200
    assert r.json()["status"] == "queued"
    worker.run_once()
    job = _job(client, job_id)
    assert job["status"] == "completed"
    assert job["attempts"] == 2
    assert job["steps"][0]["finished_at"] == first_done  # étape réussie non rejouée


def test_cancel_queued_job(client: TestClient, project_id: str, worker: Worker) -> None:
    job_id = client.post("/api/jobs", json={"project_id": project_id, "kind": "demo"}).json()["id"]
    r = client.post(f"/api/jobs/{job_id}/cancel")
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled"
    assert all(s["status"] == "cancelled" for s in r.json()["steps"])
    assert worker.run_once() is False
    assert client.post(f"/api/jobs/{job_id}/cancel").status_code == 409


def test_cancel_running_job_between_steps(
    client: TestClient,
    project_id: str,
    worker: Worker,
    session_factory: sessionmaker[Session],
) -> None:
    job_id = client.post("/api/jobs", json={"project_id": project_id, "kind": "demo"}).json()["id"]
    with session_factory() as s:
        assert claim_next_job(s, worker.worker_id) == job_id
    r = client.post(f"/api/jobs/{job_id}/cancel")
    assert r.status_code == 200
    assert r.json()["status"] == "running"
    assert r.json()["cancel_requested"] is True

    worker.process_job(job_id)
    job = _job(client, job_id)
    assert job["status"] == "cancelled"
    assert all(s["status"] == "cancelled" for s in job["steps"])

    # Relance possible après annulation.
    assert client.post(f"/api/jobs/{job_id}/retry").json()["status"] == "queued"


def test_retry_rejected_for_completed_job(
    client: TestClient, project_id: str, worker: Worker
) -> None:
    job_id = client.post("/api/jobs", json={"project_id": project_id, "kind": "demo"}).json()["id"]
    worker.run_once()
    assert client.post(f"/api/jobs/{job_id}/retry").status_code == 409


def test_claim_is_exclusive(
    client: TestClient, project_id: str, session_factory: sessionmaker[Session]
) -> None:
    client.post("/api/jobs", json={"project_id": project_id, "kind": "demo"})
    with session_factory() as s1, session_factory() as s2:
        assert claim_next_job(s1, "w1") is not None
        assert claim_next_job(s2, "w2") is None


def test_crash_recovery_resumes_without_replaying_completed_steps(
    client: TestClient,
    project_id: str,
    worker: Worker,
    session_factory: sessionmaker[Session],
) -> None:
    """Simule un worker tué en pleine étape 2, puis un redémarrage."""
    job_id = client.post("/api/jobs", json={"project_id": project_id, "kind": "demo"}).json()["id"]
    long_ago = utcnow() - timedelta(minutes=10)
    with session_factory() as s:
        assert claim_next_job(s, "worker-mort") == job_id
        steps = list(
            s.scalars(select(JobStep).where(JobStep.job_id == job_id).order_by(JobStep.position))
        )
        steps[0].status, steps[0].finished_at = "completed", long_ago
        steps[1].status, steps[1].started_at = "running", long_ago
        s.execute(update(Job).where(Job.id == job_id).values(heartbeat_at=long_ago, progress=0.25))
        s.commit()

    # Un job au battement de cœur récent n'est pas repris.
    with session_factory() as s:
        assert recover_stale_jobs(s, timedelta(hours=1)) == []

    worker.run_once()  # récupère le job abandonné puis le termine
    job = _job(client, job_id)
    assert job["status"] == "completed"
    assert job["attempts"] == 2
    assert job["steps"][0]["finished_at"] is not None
    assert job["steps"][0]["finished_at"].startswith(long_ago.strftime("%Y-%m-%dT%H:%M"))


def test_jobs_persist_across_app_restart(migrated, project_id: str, client: TestClient) -> None:
    from app.main import create_app

    job_id = client.post("/api/jobs", json={"project_id": project_id, "kind": "demo"}).json()["id"]
    with TestClient(create_app(migrated, configure_logs=False)) as c2:
        job = c2.get(f"/api/jobs/{job_id}").json()
        assert job["status"] == "queued"
        assert len(job["steps"]) == 4
