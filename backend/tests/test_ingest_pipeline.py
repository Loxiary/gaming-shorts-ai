"""Pipeline d'ingestion de bout en bout : API d'import -> worker -> base + fichiers.

yt-dlp et le modèle Whisper sont remplacés par des faux ; FFmpeg/ffprobe sont réels.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.media.ffmpeg import FfmpegTool
from app.adapters.registry import Adapters
from app.core.config import Settings
from app.models import Job, JobStep
from app.workers.errors import StepError
from app.workers.runner import Worker
from tests.fakes import FakeDownloader, FakeTranscriber, requires_ffmpeg

pytestmark = requires_ffmpeg

URL = "https://www.youtube.com/watch?v=abcdefghijk"


@pytest.fixture
def downloader() -> FakeDownloader:
    return FakeDownloader()


@pytest.fixture
def transcriber() -> FakeTranscriber:
    return FakeTranscriber()


@pytest.fixture
def ingest_worker(
    migrated: Settings,
    session_factory: sessionmaker[Session],
    downloader: FakeDownloader,
    transcriber: FakeTranscriber,
) -> Iterator[Worker]:
    yield Worker(
        migrated,
        session_factory,
        Adapters(downloader=downloader, media=FfmpegTool(), transcriber=transcriber),
    )


def _import(client: TestClient, *urls: str, **extra: object) -> list[dict]:
    r = client.post("/api/imports", json={"urls": list(urls), **extra})
    assert r.status_code == 200, r.text
    return r.json()


def _job(client: TestClient, job_id: str) -> dict:
    return client.get(f"/api/jobs/{job_id}").json()


def test_import_creates_project_source_and_job(client: TestClient) -> None:
    results = _import(
        client,
        URL,
        "https://vimeo.com/1",
        "https://youtu.be/abcdefghijk",  # même vidéo, autre forme de lien
        rights_status="owned",
        rights_note="Ma propre partie",
        game="GTA 6",
    )
    assert [r["status"] for r in results] == ["created", "rejected", "rejected"]
    assert "Seuls les liens YouTube" in results[1]["message"]
    assert "double" in results[2]["message"]

    project = client.get(f"/api/projects/{results[0]['project_id']}").json()
    assert project["game"] == "GTA 6"
    assert project["source"]["external_id"] == "abcdefghijk"
    assert project["source"]["rights_status"] == "owned"
    assert project["source"]["rights_note"] == "Ma propre partie"
    assert project["source"]["media_available"] is False
    job = _job(client, results[0]["job_id"])
    assert job["kind"] == "ingest_youtube"
    assert job["is_demo"] is False
    assert [s["name"] for s in job["steps"]] == [
        "validating_source",
        "downloading",
        "probing_media",
        "extracting_audio",
        "transcribing",
    ]

    again = _import(client, URL)
    assert again[0]["status"] == "duplicate"
    assert again[0]["project_id"] == results[0]["project_id"]


def test_import_validation(client: TestClient) -> None:
    assert client.post("/api/imports", json={"urls": []}).status_code == 422
    assert client.post("/api/imports", json={"urls": ["  "]}).status_code == 422
    r = client.post("/api/imports", json={"urls": [URL], "rights_status": "volé"})
    assert r.status_code == 422


def test_full_ingest(
    client: TestClient,
    ingest_worker: Worker,
    migrated: Settings,
    transcriber: FakeTranscriber,
) -> None:
    created = _import(client, URL)[0]
    assert ingest_worker.run_once() is True

    job = _job(client, created["job_id"])
    assert job["status"] == "completed", job
    assert job["progress"] == 1.0
    assert all(s["status"] == "completed" for s in job["steps"])
    outputs = {s["name"]: s["output"] for s in job["steps"]}
    assert outputs["probing_media"]["width"] == 320
    assert outputs["probing_media"]["has_audio"] is True
    assert outputs["transcribing"]["segments"] == 2
    assert outputs["transcribing"]["language"] == "fr"

    project = client.get(f"/api/projects/{created['project_id']}").json()
    assert project["name"] == "Partie GTA de test"  # titre récupéré depuis les métadonnées
    source = project["source"]
    assert source["uploader"] == "Chaîne de test"
    assert source["media_available"] and source["audio_available"]
    assert source["width"] == 320 and source["height"] == 240
    assert source["video_codec"] == "h264" and source["audio_codec"] == "aac"
    assert 2.5 < source["duration_seconds"] < 3.5
    assert project["transcript"]["segment_count"] == 2
    assert project["files_size_bytes"] > 0

    # Audio extrait : WAV 16 kHz mono, vérifié par ffprobe réel.
    wav = transcriber.audio_paths[0]
    probe = FfmpegTool().probe(wav)
    assert probe.audio_sample_rate == 16000 and probe.audio_channels == 1
    assert wav.is_relative_to(migrated.data_dir)

    transcript = client.get(f"/api/projects/{created['project_id']}/transcript").json()
    assert transcript["kind"] == "source"
    assert transcript["segments"][0]["text"] == "Attention, il arrive par la gauche !"
    assert transcript["segments"][0]["words"][0] == {
        "start": 0.0,
        "end": 0.6,
        "word": " Attention,",
        "probability": 0.98,
    }

    media = client.get(
        f"/api/projects/{created['project_id']}/media", headers={"Range": "bytes=0-99"}
    )
    assert media.status_code == 206
    assert len(media.content) == 100


def test_delete_project_removes_files(
    client: TestClient, ingest_worker: Worker, migrated: Settings
) -> None:
    created = _import(client, URL)[0]
    ingest_worker.run_once()
    pid = created["project_id"]
    source_dir = migrated.subdir("sources") / pid
    project_dir = migrated.subdir("projects") / pid
    assert source_dir.is_dir() and project_dir.is_dir()

    assert client.delete(f"/api/projects/{pid}?confirm=true").status_code == 204
    assert not source_dir.exists() and not project_dir.exists()
    assert migrated.subdir("sources").is_dir()  # le dossier racine est conservé
    assert _import(client, URL)[0]["status"] == "created"  # réimport possible


def test_metadata_error_fails_clearly(
    client: TestClient, ingest_worker: Worker, downloader: FakeDownloader
) -> None:
    downloader.metadata_error = StepError("Vidéo privée : elle n'est pas accessible.")
    created = _import(client, URL)[0]
    ingest_worker.run_once()
    job = _job(client, created["job_id"])
    assert job["status"] == "failed"
    assert job["error_message"] == "Vidéo privée : elle n'est pas accessible."
    assert job["steps"][0]["status"] == "failed"
    assert downloader.download_calls == 0


def test_retry_after_download_failure_resumes(
    client: TestClient, ingest_worker: Worker, downloader: FakeDownloader
) -> None:
    downloader.download_error = StepError("Connexion à YouTube impossible.")
    created = _import(client, URL)[0]
    ingest_worker.run_once()
    job = _job(client, created["job_id"])
    assert job["status"] == "failed"
    assert [s["status"] for s in job["steps"]][:2] == ["completed", "failed"]

    client.post(f"/api/jobs/{created['job_id']}/retry")
    ingest_worker.run_once()
    job = _job(client, created["job_id"])
    assert job["status"] == "completed"
    assert downloader.metadata_calls == 1  # validation non rejouée
    assert downloader.download_calls == 2


def test_download_step_reuses_existing_file(
    client: TestClient,
    ingest_worker: Worker,
    downloader: FakeDownloader,
    session_factory: sessionmaker[Session],
) -> None:
    """Crash après le téléchargement mais avant la fin de l'étape : pas de 2e téléchargement."""
    created = _import(client, URL)[0]
    ingest_worker.run_once()
    with session_factory() as s:  # simule des étapes 2..5 non validées
        s.execute(
            update(JobStep)
            .where(JobStep.job_id == created["job_id"], JobStep.position >= 1)
            .values(status="pending")
        )
        s.execute(update(Job).where(Job.id == created["job_id"]).values(status="queued"))
        s.commit()
    ingest_worker.run_once()
    job = _job(client, created["job_id"])
    assert job["status"] == "completed"
    assert downloader.download_calls == 1
    downloading = next(s for s in job["steps"] if s["name"] == "downloading")
    assert downloading["output"]["reused"] is True


def test_cancel_during_download(
    client: TestClient, ingest_worker: Worker, downloader: FakeDownloader
) -> None:
    created = _import(client, URL)[0]
    downloader.cancel_during_download = True
    downloader.on_cancel_point = lambda: client.post(f"/api/jobs/{created['job_id']}/cancel")
    ingest_worker.run_once()
    job = _job(client, created["job_id"])
    assert job["status"] == "cancelled"
    statuses = [s["status"] for s in job["steps"]]
    assert statuses == ["completed", "cancelled", "cancelled", "cancelled", "cancelled"]

    downloader.cancel_during_download = False
    client.post(f"/api/jobs/{created['job_id']}/retry")
    ingest_worker.run_once()
    assert _job(client, created["job_id"])["status"] == "completed"


def test_video_without_audio_fails_at_probe(
    client: TestClient, ingest_worker: Worker, downloader: FakeDownloader
) -> None:
    downloader.audio = False
    created = _import(client, URL)[0]
    ingest_worker.run_once()
    job = _job(client, created["job_id"])
    assert job["status"] == "failed"
    assert "piste audio" in job["error_message"]
    assert job["current_step"] is None


def test_update_rights_status_is_informative(client: TestClient) -> None:
    created = _import(client, URL)[0]
    pid = created["project_id"]
    r = client.patch(
        f"/api/projects/{pid}/source",
        json={"rights_status": "authorized", "rights_note": "Accord écrit du créateur"},
    )
    assert r.status_code == 200
    assert r.json()["rights_status"] == "authorized"
    assert (
        client.patch(f"/api/projects/{pid}/source", json={"rights_status": "x"}).status_code == 422
    )
    assert client.get(f"/api/projects/{pid}/transcript").status_code == 404
    assert client.get(f"/api/projects/{pid}/media").status_code == 404
