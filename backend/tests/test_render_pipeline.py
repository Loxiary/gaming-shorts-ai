"""Montage de bout en bout : import -> analyse -> montage (FFmpeg réel) -> QC -> export.

IA simulée (FakeJudge, FakeEditor) ; aucun appel payant. Rendu en preset x264 « ultrafast ».
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.media.ffmpeg import FfmpegTool
from app.adapters.registry import Adapters
from app.core.config import Settings
from app.services import budget
from app.workers.runner import Worker
from tests.fakes import (
    FakeDownloader,
    FakeEditor,
    FakeJudge,
    SpeechTranscriber,
    make_bursty_video,
    requires_ffmpeg,
)

pytestmark = requires_ffmpeg
URL = "https://www.youtube.com/watch?v=abcdefghijk"
SECONDS = 100.0


@pytest.fixture(scope="module")
def video(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return make_bursty_video(tmp_path_factory.mktemp("media") / "v.mp4", SECONDS, bursts=(30, 70))


@pytest.fixture
def fast_settings(migrated: Settings) -> Settings:
    migrated.render_x264_preset = "ultrafast"
    migrated.frames_per_candidate = 2
    return migrated


class _Copy(FakeDownloader):
    def __init__(self, src: Path) -> None:
        super().__init__(seconds=SECONDS)
        self.src = src

    def download(self, url, dest_dir, on_progress, check_cancel):  # type: ignore[no-untyped-def]
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(self.src, dest_dir / "source.mp4")
        return dest_dir / "source.mp4"


def _worker(settings: Settings, sf: sessionmaker[Session], video: Path, editor) -> Worker:  # type: ignore[no-untyped-def]
    return Worker(
        settings,
        sf,
        Adapters(
            downloader=_Copy(video),
            media=FfmpegTool(),
            transcriber=SpeechTranscriber(SECONDS),
            judge=FakeJudge(score=8),
            editor=editor,
        ),
    )


def _candidate(client: TestClient, worker: Worker) -> tuple[str, dict]:
    created = client.post("/api/imports", json={"urls": [URL]}).json()[0]
    worker.run_once()
    pid = created["project_id"]
    analysis = client.post(f"/api/projects/{pid}/analyses", json={}).json()
    worker.run_once()
    full = client.get(f"/api/analyses/{analysis['id']}").json()
    assert full["candidates"], full
    return pid, full["candidates"][0]


def _render(client: TestClient, worker: Worker, candidate_id: str) -> dict:
    r = client.post(f"/api/candidates/{candidate_id}/renders", json={})
    assert r.status_code == 201, r.text
    worker.run_once()
    return client.get(f"/api/renders/{r.json()['id']}").json()


def _profile_update(client: TestClient, **changes: object) -> None:
    profile = next(p for p in client.get("/api/profiles").json() if p["is_default"])
    body = {k: v for k, v in profile.items() if k not in {"id", "created_at", "updated_at"}}
    r = client.put(f"/api/profiles/{profile['id']}", json=body | changes)
    assert r.status_code == 200, r.text


def test_full_render_qc_and_confirmed_export(
    client: TestClient, fast_settings: Settings, session_factory: sessionmaker[Session], video: Path
) -> None:
    editor = FakeEditor()
    worker = _worker(fast_settings, session_factory, video, editor)
    pid, cand = _candidate(client, worker)
    render = _render(client, worker, cand["id"])

    assert render["job_status"] == "completed", render["job_error"]
    assert render["plan_engine"] == "llm"
    assert render["plan"]["hook_text"] == "Une partie qui démarre fort"
    assert render["subtitles"] and not render["subtitles_are_translation"]
    assert render["qc_passed"] is True and render["ready"] is True
    checks = {c["key"]: c for c in render["qc"]["checks"]}
    for key in ("file", "duration", "resolution", "video_codec", "audio", "decode", "pix_fmt"):
        assert checks[key]["ok"], checks[key]
    assert abs(render["qc"]["measures"]["integrated_lufs"] + 14) < 2.5

    # Fichier réellement vertical, H.264/AAC, à la durée de l'extrait.
    probe = FfmpegTool().probe(
        fast_settings.resolve_data_path(f"projects/{pid}/renders/{render['id']}/short.mp4")
    )
    assert (probe.width, probe.height) == (1080, 1920)
    assert probe.video_codec == "h264" and probe.audio_codec == "aac"
    assert abs(probe.duration_seconds - render["duration_seconds"]) < 0.25
    assert 61 <= probe.duration_seconds <= 180

    risk = render["risk_report"]
    assert risk["blocking"] is False and risk["reused_content"]["level"] == "élevé"
    assert "Droits sur la source non vérifiés." in render["export_warnings"]
    assert any(w.startswith("Accroche originale") for w in render["export_warnings"])
    assert render["cost_usd"] == pytest.approx(0.009)  # 1 appel fictif : 2000 + 500 jetons

    video_resp = client.get(render["video_url"], headers={"Range": "bytes=0-99"})
    assert video_resp.status_code == 206

    # Export : confirmation obligatoire, malgré des risques élevés jamais bloquants.
    r = client.post(f"/api/renders/{render['id']}/confirm-export", json={"acknowledged": False})
    assert r.status_code == 400
    r = client.post(f"/api/renders/{render['id']}/confirm-export", json={"acknowledged": True})
    assert r.status_code == 200, r.text
    exported = r.json()
    assert exported["export_status"] == "exported"
    out = Path(exported["exported_path"])
    assert out.is_file() and out.parent == fast_settings.subdir("exports")
    sidecar = json.loads(out.with_suffix(".json").read_text(encoding="utf-8"))
    assert sidecar["source"]["url"] == "https://www.youtube.com/watch?v=abcdefghijk"
    assert sidecar["acknowledged_warnings"] == exported["acknowledged_warnings"]
    assert (
        client.post(
            f"/api/renders/{render['id']}/confirm-export", json={"acknowledged": True}
        ).status_code
        == 409
    )
    assert [e["id"] for e in client.get("/api/exports").json()] == [render["id"]]

    # Supprimer le rendu (ou le projet) conserve le fichier exporté.
    assert client.delete(f"/api/renders/{render['id']}?confirm=true").status_code == 204
    assert client.delete(f"/api/projects/{pid}?confirm=true").status_code == 204
    assert out.is_file()


def test_translation_and_profile_settings(
    client: TestClient, fast_settings: Settings, session_factory: sessionmaker[Session], video: Path
) -> None:
    editor = FakeEditor(hook_kind="original")
    worker = _worker(fast_settings, session_factory, video, editor)
    _, cand = _candidate(client, worker)
    # Transcription simulée en « fr » : traduction vers l'anglais demandée.
    _profile_update(
        client,
        subtitle_mode="translate",
        output_language="en",
        layout="fill",
        cta_enabled=False,
        subtitle_style={"font": "Impact", "max_words": 2},
    )
    render = _render(client, worker, cand["id"])
    assert render["job_status"] == "completed", render["job_error"]
    assert render["subtitles_are_translation"] is True and render["subtitle_language"] == "en"
    assert render["subtitles"][0]["text"].startswith("Phrase")
    assert render["plan"]["cta_text"] == ""
    assert editor.calls == ["EditorialPlan", "Translation"]


def test_without_ai_uses_fallback_plan(
    client: TestClient, fast_settings: Settings, session_factory: sessionmaker[Session], video: Path
) -> None:
    worker = _worker(fast_settings, session_factory, video, editor=None)
    _, cand = _candidate(client, worker)
    _profile_update(client, subtitle_mode="translate", output_language="en")
    render = _render(client, worker, cand["id"])
    assert render["job_status"] == "completed", render["job_error"]
    assert render["plan_engine"] == "fallback"
    assert render["plan"]["hook_kind"] == "quote"
    assert any("sans IA" in w for w in render["plan"]["warnings"])
    assert any("Traduction impossible" in w for w in render["plan"]["warnings"])
    assert render["subtitles_are_translation"] is False
    assert render["cost_usd"] == 0


def test_budget_cap_falls_back_without_spending(
    client: TestClient, fast_settings: Settings, session_factory: sessionmaker[Session], video: Path
) -> None:
    editor = FakeEditor()
    worker = _worker(fast_settings, session_factory, video, editor)
    _, cand = _candidate(client, worker)
    with session_factory() as s:
        budget.set_setting(s, budget.MONTHLY_CAP, 0.0)
    render = _render(client, worker, cand["id"])
    assert render["job_status"] == "completed"
    assert render["plan_engine"] == "fallback" and editor.calls == []
    assert any("Plafond" in w for w in render["plan"]["warnings"])


def test_render_guards(
    client: TestClient, fast_settings: Settings, session_factory: sessionmaker[Session], video: Path
) -> None:
    worker = _worker(fast_settings, session_factory, video, FakeEditor())
    _, cand = _candidate(client, worker)
    first = client.post(f"/api/candidates/{cand['id']}/renders", json={})
    assert first.status_code == 201
    dup = client.post(f"/api/candidates/{cand['id']}/renders", json={})
    assert dup.status_code == 409  # même extrait déjà en file
    # Un rendu non terminé ne peut pas être exporté.
    r = client.post(
        f"/api/renders/{first.json()['id']}/confirm-export", json={"acknowledged": True}
    )
    assert r.status_code == 409
    assert client.post("/api/candidates/inexistant/renders", json={}).status_code == 404
    r = client.post("/api/jobs", json={"project_id": cand["id"], "kind": "render_clip"})
    assert r.status_code in {400, 404}
