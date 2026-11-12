"""Phase 6 : pause/reprise, réglages globaux, stockage et nettoyage, sauvegarde/restauration,
export/import des profils."""

from __future__ import annotations

import json
import os
import sqlite3
import time
import zipfile
from datetime import timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.time import utcnow
from app.models import ClipRender, Job, SourceMedia
from app.services.queue import claim_next_job
from app.workers.runner import Worker
from tests.fakes import requires_ffmpeg

# --------------------------------------------------------------------------- pause


def _demo(client: TestClient, project_id: str) -> str:
    r = client.post("/api/jobs", json={"project_id": project_id, "kind": "demo"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_pause_queued_job_then_resume(client: TestClient, worker: Worker, project_id: str) -> None:
    job_id = _demo(client, project_id)
    r = client.post(f"/api/jobs/{job_id}/pause").json()
    assert r["status"] == "paused"
    assert worker.run_once() is False  # un job en pause n'est jamais pris par le worker
    counts = client.get(f"/api/projects/{project_id}").json()["job_counts"]
    assert counts["paused"] == 1 and counts["total"] == 1
    # En pause = toujours actif : pas de doublon du même type.
    assert (
        client.post("/api/jobs", json={"project_id": project_id, "kind": "demo"}).status_code == 409
    )
    assert client.post(f"/api/jobs/{job_id}/resume").json()["status"] == "queued"
    worker.run_once()
    assert client.get(f"/api/jobs/{job_id}").json()["status"] == "completed"
    assert client.post(f"/api/jobs/{job_id}/pause").status_code == 409
    assert client.post(f"/api/jobs/{job_id}/resume").status_code == 409


def test_running_job_pauses_between_steps_and_keeps_completed_steps(
    client: TestClient, worker: Worker, project_id: str, session_factory: sessionmaker[Session]
) -> None:
    job_id = _demo(client, project_id)
    with session_factory() as s:
        assert claim_next_job(s, worker.worker_id) == job_id
        steps = s.get(Job, job_id).steps  # type: ignore[union-attr]
        steps[0].status = "completed"  # une étape déjà faite avant la pause
        s.commit()
    r = client.post(f"/api/jobs/{job_id}/pause").json()
    assert r["status"] == "running" and r["pause_requested"] is True
    worker.process_job(job_id)  # s'arrête avant l'étape suivante
    job = client.get(f"/api/jobs/{job_id}").json()
    assert job["status"] == "paused" and job["pause_requested"] is False
    assert [s["status"] for s in job["steps"]][:2] == ["completed", "pending"]
    client.post(f"/api/jobs/{job_id}/resume")
    worker.run_once()
    job = client.get(f"/api/jobs/{job_id}").json()
    assert job["status"] == "completed" and all(s["status"] == "completed" for s in job["steps"])


def test_paused_job_can_be_cancelled(client: TestClient, project_id: str) -> None:
    job_id = _demo(client, project_id)
    client.post(f"/api/jobs/{job_id}/pause")
    assert client.post(f"/api/jobs/{job_id}/cancel").json()["status"] == "cancelled"


# --------------------------------------------------------------------------- réglages


def test_runtime_settings_validate_override_and_reset(client: TestClient, worker: Worker) -> None:
    items = {i["key"]: i for i in client.get("/api/settings/runtime").json()}
    assert "anthropic_api_key" not in items and "data_dir" not in items
    assert (
        items["frames_per_candidate"]["value"] == 8
        and not items["frames_per_candidate"]["overridden"]
    )
    assert items["llm_effort"]["choices"] == ["low", "medium", "high"]

    r = client.put(
        "/api/settings/runtime",
        json={"values": {"frames_per_candidate": 3, "retention_auto": True}},
    )
    assert r.status_code == 200
    items = {i["key"]: i for i in r.json()}
    assert (
        items["frames_per_candidate"]["value"] == 3 and items["frames_per_candidate"]["overridden"]
    )
    assert items["frames_per_candidate"]["env_value"] == 8

    for bad in (
        {"frames_per_candidate": 99},
        {"llm_effort": "max"},
        {"data_dir": "C:/"},
        {"whisper_language": "français"},
    ):
        assert client.put("/api/settings/runtime", json={"values": bad}).status_code == 400, bad

    worker.refresh_settings()  # appliqué au début du job suivant
    assert worker.settings.frames_per_candidate == 3 and worker.settings.retention_auto is True
    client.put("/api/settings/runtime", json={"values": {"frames_per_candidate": None}})
    worker.refresh_settings()
    assert worker.settings.frames_per_candidate == 8


# --------------------------------------------------------------------------- stockage


def _old(path: Path, days: float) -> Path:
    t = time.time() - days * 86400
    os.utime(path, (t, t))
    return path


def _file(path: Path, size: int = 1000, days: float | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    return _old(path, days) if days is not None else path


def test_storage_usage_and_cleanup_preview_then_confirm(
    client: TestClient, migrated: Settings, session_factory: sessionmaker[Session], project_id: str
) -> None:
    data = migrated.data_dir
    long_ago = utcnow() - timedelta(days=60)
    # Projet inactif depuis 60 j : source, audio, copie d'analyse, un rendu terminé non exporté.
    src = _file(data / "sources" / project_id / "source.mp4", 50_000)
    wav = _file(data / "projects" / project_id / "audio_16k_mono.wav", 5_000)
    proxy = _file(data / "projects" / project_id / "analysis" / "proxy_480p.mp4", 4_000, days=30)
    frame = _file(data / "projects" / project_id / "analysis" / "a1" / "frames" / "0.jpg", 100, 30)
    with session_factory() as s:
        s.add(
            SourceMedia(
                project_id=project_id,
                source_type="youtube",
                url="https://y/v",
                external_id="abcdefghijk",
                media_path=f"sources/{project_id}/source.mp4",
                audio_path=f"projects/{project_id}/audio_16k_mono.wav",
            )
        )
        job = Job(
            project_id=project_id,
            kind="render_clip",
            status="completed",
            finished_at=long_ago,
            updated_at=long_ago,
        )
        s.add(job)
        s.flush()
        r = ClipRender(
            project_id=project_id,
            job_id=job.id,
            start_seconds=0,
            end_seconds=70,
            profile_snapshot_json="{}",
            created_at=long_ago,
            output_path=f"projects/{project_id}/renders/R/short.mp4",
        )
        s.add(r)
        s.flush()
        rid = r.id
        s.commit()
    work = data / "projects" / project_id / "renders" / rid
    short = _file(work / "short.mp4", 20_000)
    mixwav = _file(work / "audio_mix.wav", 3_000)
    _file(work / "facecam" / "00.jpg", 50)
    with session_factory() as s:
        s.get(ClipRender, rid).output_path = f"projects/{project_id}/renders/{rid}/short.mp4"  # type: ignore[union-attr]
        s.commit()
    tmp_old = _file(data / "temp" / "vieux.bin", 2_000, days=10)
    tmp_new = _file(data / "temp" / "recent.bin", 2_000)
    export = _file(data / "exports" / "short.mp4", 7_000, days=400)
    _file(data / "gaming_shorts.backup-avant-0002.db", 300, days=20)
    _file(data / "gaming_shorts.backup-avant-0005.db", 300, days=1)

    usage = client.get("/api/storage").json()
    proj = next(p for p in usage["projects"] if p["project_id"] == project_id)
    assert proj["source_bytes"] == 55_000 and proj["renders_bytes"] > 23_000
    assert usage["db_backups_bytes"] == 600 and usage["retention"]["temp_days"] == 7

    # Délais par défaut : seuls les intermédiaires (7 j) ; sources et rendus = jamais.
    prev = client.post("/api/storage/cleanup", json={"categories": ["temp", "renders", "sources"]})
    paths = {i["path"] for i in prev.json()["items"]}
    assert paths == {
        "temp/vieux.bin",
        f"projects/{project_id}/analysis/proxy_480p.mp4",
        f"projects/{project_id}/renders/{rid}/audio_mix.wav",
        f"projects/{project_id}/renders/{rid}/facecam",
    }
    assert tmp_old.exists() and mixwav.exists()  # aperçu : rien n'est supprimé

    client.put(
        "/api/settings/runtime",
        json={"values": {"retention_source_days": 30, "retention_render_days": 30}},
    )
    done = client.post(
        "/api/storage/cleanup",
        json={"categories": ["temp", "renders", "sources", "db_backups"], "dry_run": False},
    ).json()
    assert done["errors"] == [] and done["bytes"] > 80_000
    for gone in (tmp_old, proxy, mixwav, src, wav, short):
        assert not gone.exists(), gone
    for kept in (
        tmp_new,
        export,
        frame,
        data / "gaming_shorts.backup-avant-0005.db",
        migrated.db_path,
    ):
        assert kept.exists(), kept
    assert not (data / "gaming_shorts.backup-avant-0002.db").exists()

    # Les fiches restent ; les chemins disparus sont effacés, le rendu est marqué nettoyé.
    detail = client.get(f"/api/projects/{project_id}").json()
    assert detail["source"]["media_available"] is False
    render = client.get(f"/api/renders/{rid}").json()
    assert render["files_purged"] is True and render["video_url"] is None and not render["ready"]

    refused = client.post("/api/storage/cleanup", json={"categories": ["exports"]})
    assert refused.status_code == 400  # exports, modèles, musique : jamais nettoyables


def test_cleanup_never_touches_busy_projects(
    client: TestClient, migrated: Settings, project_id: str
) -> None:
    proxy = _file(
        migrated.data_dir / "projects" / project_id / "analysis" / "proxy_480p.mp4", 4_000, days=30
    )
    client.post("/api/jobs", json={"project_id": project_id, "kind": "demo"})  # en attente
    prev = client.post("/api/storage/cleanup", json={"categories": ["temp"]}).json()
    assert prev["items"] == []
    client.post("/api/storage/cleanup", json={"categories": ["temp"], "dry_run": False})
    assert proxy.exists()


def test_auto_cleanup_only_when_enabled(
    client: TestClient, migrated: Settings, worker: Worker
) -> None:
    old = _file(migrated.data_dir / "temp" / "x.bin", 10, days=30)
    worker.run_once()
    assert old.exists()  # désactivé par défaut
    client.put("/api/settings/runtime", json={"values": {"retention_auto": True}})
    worker.run_once()
    assert not old.exists()


# --------------------------------------------------------------------------- sauvegardes


def test_backup_contains_db_and_settings_but_no_secret(
    client: TestClient, migrated: Settings, project_id: str
) -> None:
    secret = "sk-ant-test-secret-ne-doit-pas-fuiter"
    migrated.anthropic_api_key = secret  # type: ignore[assignment]
    client.put("/api/settings/runtime", json={"values": {"whisper_beam_size": 2}})
    b = client.post("/api/backups")
    assert b.status_code == 201, b.text
    info = b.json()
    assert info["valid"] and info["counts"]["projects"] == 1 and info["schema_revision"] == "0010"
    assert [x["name"] for x in client.get("/api/backups").json()] == [info["name"]]

    resp = client.get(f"/api/backups/{info['name']}")
    assert resp.status_code == 200
    archive = migrated.data_dir / "dl.zip"
    archive.write_bytes(resp.content)
    with zipfile.ZipFile(archive) as z:
        assert set(z.namelist()) == {
            "gaming_shorts.db",
            "profiles.json",
            "settings.json",
            "manifest.json",
        }
        doc = json.loads(z.read("settings.json"))
        assert doc["runtime_overrides"] == {"whisper_beam_size": 2}
        assert doc["config"]["anthropic_api_key_configured"] is True
        for name in z.namelist():
            assert secret.encode() not in z.read(name)
        assert len(json.loads(z.read("profiles.json"))) == 5

    assert client.get("/api/backups/..%2F.env").status_code in (400, 404)
    assert client.delete(f"/api/backups/{info['name']}").status_code == 400
    assert client.delete(f"/api/backups/{info['name']}?confirm=true").status_code == 204
    assert client.get("/api/backups").json() == []


def test_restore_replaces_database_with_safety_copy(
    client: TestClient, migrated: Settings, project_id: str
) -> None:
    from app.cli.backup import restore

    name = client.post("/api/backups").json()["name"]
    archive = migrated.data_dir / "backups" / name
    client.post("/api/projects", json={"name": "Créé après la sauvegarde"})
    assert len(client.get("/api/projects").json()) == 2
    client.app.state.engine.dispose()  # type: ignore[attr-defined]  # « application arrêtée »

    offline = migrated.model_copy(update={"api_port": 1})  # port fermé : « application arrêtée »
    assert restore(archive, yes=True, settings=offline) == 0
    con = sqlite3.connect(str(migrated.db_path))
    names = [r[0] for r in con.execute("SELECT name FROM projects")]
    con.close()
    assert names == ["Projet test"]
    assert list(migrated.data_dir.glob("gaming_shorts.avant-restauration-*.db"))

    bad = migrated.data_dir / "pas-une-sauvegarde.zip"
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("autre.txt", "x")
    assert restore(bad, yes=True, settings=offline) == 2


def test_profiles_export_and_import(client: TestClient) -> None:
    doc = client.get("/api/profiles-export").json()
    assert doc["format"] == "gaming-shorts-ai/profiles" and len(doc["profiles"]) == 5
    assert "id" not in doc["profiles"][0]
    r = client.post("/api/profiles-import", json={**doc, "profiles": doc["profiles"][:2]})
    assert r.status_code == 201, r.text
    names = [p["name"] for p in r.json()]
    assert all(n.endswith("(importé)") for n in names)
    assert not any(p["is_default"] for p in r.json())
    assert len(client.get("/api/profiles").json()) == 7

    assert client.post("/api/profiles-import", json={"profiles": []}).status_code == 400
    broken = {**doc, "profiles": [{**doc["profiles"][0], "threshold": 500}]}
    r = client.post("/api/profiles-import", json=broken)
    assert r.status_code == 400 and "threshold" in r.json()["error"]["message"]
    assert len(client.get("/api/profiles").json()) == 7  # tout ou rien


# --------------------------------------------------------------------------- montage en lot


@requires_ffmpeg
def test_batch_render_of_selected_candidates_skips_already_rendered(
    client: TestClient, migrated: Settings, session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    from tests.fakes import FakeEditor, make_bursty_video
    from tests.test_render_pipeline import SECONDS, _candidate, _worker

    video = make_bursty_video(tmp_path / "v.mp4", SECONDS, bursts=(30, 70))
    worker = _worker(migrated, session_factory, video, FakeEditor())
    pid, _ = _candidate(client, worker)
    analysis = client.get(f"/api/projects/{pid}/analyses").json()[0]
    full = client.get(f"/api/analyses/{analysis['id']}").json()
    selected = [c["id"] for c in full["candidates"] if c["selected"]]
    assert selected

    r = client.post(f"/api/analyses/{analysis['id']}/renders", json={})
    assert r.status_code == 201, r.text
    assert sorted(x["candidate_id"] for x in r.json()["created"]) == sorted(selected)
    again = client.post(f"/api/analyses/{analysis['id']}/renders", json={}).json()
    assert again["created"] == [] and sorted(again["skipped_candidate_ids"]) == sorted(selected)
    assert client.post("/api/analyses/inconnue/renders", json={}).status_code == 404


def test_backup_works_on_older_schema_before_migration(
    migrated: Settings, session_factory: sessionmaker[Session]
) -> None:
    """Sauvegarder juste AVANT une migration : la base n'a pas encore les nouvelles colonnes."""
    from app.services import backup
    from app.services.profiles import ensure_default_profiles

    with session_factory() as s:
        ensure_default_profiles(s)
    con = sqlite3.connect(str(migrated.db_path))
    con.execute("ALTER TABLE editing_profiles DROP COLUMN sfx_level_db")  # simule un schéma ancien
    con.commit()
    con.close()
    with session_factory() as s:
        info = backup.create_backup(s, migrated)
    assert info["valid"] and info["counts"]["profiles"] == 5
