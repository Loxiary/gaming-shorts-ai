"""Analyse de bout en bout : import (faux YouTube) -> analyse -> candidats -> sélection.

FFmpeg réel (proxy, scènes, images) ; IA simulée (FakeJudge), aucun appel payant.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.media.ffmpeg import FfmpegTool
from app.adapters.registry import Adapters
from app.core.config import Settings
from app.models import ApiUsage
from app.services import budget
from app.workers.runner import Worker
from tests.fakes import (
    FakeDownloader,
    FakeJudge,
    SpeechTranscriber,
    make_bursty_video,
    requires_ffmpeg,
)

pytestmark = requires_ffmpeg
URL = "https://www.youtube.com/watch?v=abcdefghijk"
SECONDS = 150.0


@pytest.fixture(scope="module")
def bursty_video(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return make_bursty_video(tmp_path_factory.mktemp("media") / "bursty.mp4", SECONDS)


class _CopyDownloader(FakeDownloader):
    def __init__(self, video: Path, seconds: float) -> None:
        super().__init__(seconds=seconds)
        self.video = video

    def download(self, url, dest_dir, on_progress, check_cancel):  # type: ignore[no-untyped-def]
        dest_dir.mkdir(parents=True, exist_ok=True)
        dst = dest_dir / "source.mp4"
        shutil.copyfile(self.video, dst)
        return dst


def _worker(settings: Settings, sf: sessionmaker[Session], video: Path, judge, seconds=SECONDS):  # type: ignore[no-untyped-def]
    return Worker(
        settings,
        sf,
        Adapters(
            downloader=_CopyDownloader(video, seconds),
            media=FfmpegTool(),
            transcriber=SpeechTranscriber(seconds),
            judge=judge,
        ),
    )


def _imported_project(client: TestClient, worker: Worker) -> str:
    created = client.post("/api/imports", json={"urls": [URL]}).json()[0]
    worker.run_once()
    assert client.get(f"/api/jobs/{created['job_id']}").json()["status"] == "completed"
    return created["project_id"]


def _analyze(client: TestClient, worker: Worker, pid: str, **body: object) -> dict:
    r = client.post(f"/api/projects/{pid}/analyses", json=body)
    assert r.status_code == 201, r.text
    analysis = r.json()
    worker.run_once()
    analysis["job"] = client.get(f"/api/jobs/{analysis['job_id']}").json()
    analysis["full"] = client.get(f"/api/analyses/{analysis['id']}").json()
    return analysis


def test_analysis_requires_finished_import(client: TestClient) -> None:
    pid = client.post("/api/imports", json={"urls": [URL]}).json()[0]["project_id"]
    r = client.post(f"/api/projects/{pid}/analyses", json={})
    assert r.status_code == 400
    assert "import" in r.json()["error"]["message"]
    r = client.post("/api/jobs", json={"project_id": pid, "kind": "analyze_clips"})
    assert r.status_code == 400


def test_full_analysis_with_ai(
    client: TestClient,
    migrated: Settings,
    session_factory: sessionmaker[Session],
    bursty_video: Path,
) -> None:
    judge = FakeJudge(score=8)
    worker = _worker(migrated, session_factory, bursty_video, judge)
    pid = _imported_project(client, worker)

    estimate = client.get(f"/api/projects/{pid}/analysis-estimate").json()
    assert estimate["expected_candidates"] >= 1 and estimate["estimated_cost_usd"] > 0

    a = _analyze(client, worker, pid)
    job = a["job"]
    assert job["status"] == "completed", job
    assert [s["name"] for s in job["steps"]] == [
        "preparing_proxy",
        "detecting_scenes",
        "analyzing_audio",
        "generating_candidates",
        "sampling_frames",
        "scoring_candidates",
        "selecting_clips",
    ]
    full = a["full"]
    assert full["profile_name"] == "GTA 6 — Viral"
    assert full["engine"] == "llm" and full["llm_model"] == "fake-claude"
    cands = full["candidates"]
    assert cands and judge.calls == len(cands)
    for c in cands:
        assert 61 <= c["duration_seconds"] <= 90
        assert c["status"] == "scored"
        assert len(c["scores"]) == 7 and c["overall_score"] == 80.0
        assert c["summary"] and c["reason"] and c["confidence"] == 0.8
        assert c["frames"] and len(c["frames"]) <= migrated.frames_per_candidate
    assert any(c["selected"] for c in cands)  # 80 >= seuil 65

    # Les images sont réelles et servies par l'API.
    img = client.get(cands[0]["frames"][0]["url"])
    assert img.status_code == 200 and img.content[:2] == b"\xff\xd8"
    # L'IA a bien reçu les images horodatées et la transcription autour de l'extrait.
    assert judge.inputs[0].frames and judge.inputs[0].transcript

    # Coûts enregistrés par appel et cumulés sur l'analyse.
    with session_factory() as s:
        rows = list(s.scalars(select(ApiUsage)))
    assert len(rows) == len(cands) and all(r.status == "ok" for r in rows)
    assert full["cost_usd"] == pytest.approx(len(cands) * 0.02, rel=1e-3)
    costs = client.get("/api/costs").json()
    assert costs["calls_this_month"] == len(cands)

    # Changer le seuil recalcule la sélection sans rappeler l'IA.
    r = client.post(f"/api/analyses/{a['id']}/reselect", json={"threshold": 90}).json()
    assert not any(c["selected"] for c in r["candidates"])
    assert all("Sous le seuil" in c["rejection_reason"] for c in r["candidates"])
    assert judge.calls == len(cands)

    # Deuxième analyse : proxy et scènes réutilisés.
    b = _analyze(client, worker, pid)
    outputs = {s["name"]: s["output"] for s in b["job"]["steps"]}
    assert outputs["preparing_proxy"]["reused"] is True
    assert outputs["detecting_scenes"]["reused"] is True


def test_without_api_key_falls_back_to_signals(
    client: TestClient,
    migrated: Settings,
    session_factory: sessionmaker[Session],
    bursty_video: Path,
) -> None:
    worker = _worker(migrated, session_factory, bursty_video, judge=None)
    pid = _imported_project(client, worker)
    a = _analyze(client, worker, pid)
    full = a["full"]
    assert a["job"]["status"] == "completed"
    assert full["engine"] == "signals"
    assert any("sans IA" in n for n in full["notes"])
    for c in full["candidates"]:
        assert c["status"] == "signals_only"
        assert any("sans IA" in w for w in c["warnings"])
        assert c["confidence"] == 0.25 and len(c["scores"]) == 7

    r = client.post(f"/api/projects/{pid}/analyses", json={"engine": "llm"})
    worker.run_once()
    job = client.get(f"/api/jobs/{r.json()['job_id']}").json()
    assert job["status"] == "failed" and "clé API absente" in job["error_message"]


def test_budget_cap_switches_to_signals(
    client: TestClient,
    migrated: Settings,
    session_factory: sessionmaker[Session],
    bursty_video: Path,
) -> None:
    judge = FakeJudge()
    worker = _worker(migrated, session_factory, bursty_video, judge)
    pid = _imported_project(client, worker)
    with session_factory() as s:
        budget.set_setting(s, budget.MONTHLY_CAP, 0.0)
    full = _analyze(client, worker, pid)["full"]
    assert judge.calls == 0
    assert full["engine"] == "signals"
    assert any("Plafond" in n for n in full["notes"])
    assert all(c["status"] == "signals_only" for c in full["candidates"])


def test_resume_does_not_pay_twice(
    client: TestClient,
    migrated: Settings,
    session_factory: sessionmaker[Session],
    bursty_video: Path,
) -> None:
    judge = FakeJudge(fail_on={2})
    worker = _worker(migrated, session_factory, bursty_video, judge)
    pid = _imported_project(client, worker)
    a = _analyze(client, worker, pid)
    assert a["job"]["status"] == "failed"
    assert "Connexion" in a["job"]["error_message"]
    n = len(a["full"]["candidates"])
    assert n >= 2

    client.post(f"/api/jobs/{a['job_id']}/retry")
    worker.run_once()
    assert client.get(f"/api/jobs/{a['job_id']}").json()["status"] == "completed"
    # 1 réussi + 1 échec au premier passage, puis n-1 au second : jamais 2x le premier.
    assert judge.calls == 1 + 1 + (n - 1)
    with session_factory() as s:
        assert len(list(s.scalars(select(ApiUsage)))) == n


def test_too_short_video_produces_clear_note(
    client: TestClient, migrated: Settings, session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    short = make_bursty_video(tmp_path / "short.mp4", 45.0, bursts=(20,))
    worker = _worker(migrated, session_factory, short, FakeJudge(), seconds=45.0)
    pid = _imported_project(client, worker)
    a = _analyze(client, worker, pid)
    assert a["job"]["status"] == "completed"
    assert a["full"]["candidates"] == []
    assert any("moins que la durée minimale" in n for n in a["full"]["notes"])
