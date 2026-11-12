"""Durée maximale de 90 s et censure des mots grossiers dans les textes affichés."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.models import MAX_CLIP_SECONDS, ClipCandidate
from app.render.profanity import censor_text, is_profane
from tests.fakes import FakeEditor, make_bursty_video, requires_ffmpeg

# --------------------------------------------------------------------------- censure


@pytest.mark.parametrize(
    ("text", "expected", "count"),
    [
        ("Putain, c'est quoi ce bordel ?", "Pu****, c'est quoi ce bo**** ?", 2),
        ("What the FUCK, this is fucking insane!", "What the FU**, this is fu***** insane!", 2),
        ("Quel enfoiré, d'enculé", "Quel en*****, d'en****", 2),
        ("Ce con, ce cul", "Ce co*, ce cu*", 2),
        ("Shit.", "Sh**.", 1),
        # Faux positifs évités : mots entiers seulement pour les mots courts.
        ("The class assembled a classic cockpit", "The class assembled a classic cockpit", 0),
        ("Ce conseil de consulter la culture", "Ce conseil de consulter la culture", 0),
        ("He passed the assessment", "He passed the assessment", 0),
        ("", "", 0),
        # Insultes racistes / homophobes : toujours masquées (et bipées au mixage).
        ("Yo nigga, what up?", "Yo ni***, what up?", 1),
        ("Niggas everywhere, faggot", "Ni**** everywhere, fa****", 2),
        (
            "We negotiate in Nigeria and Niger tonight",
            "We negotiate in Nigeria and Niger tonight",
            0,
        ),
    ],
)
def test_censor_keeps_two_letters_and_masks_the_rest(text: str, expected: str, count: int) -> None:
    assert censor_text(text) == (expected, count)


def test_profanity_detection_ignores_case_and_accents() -> None:
    assert is_profane("ENCULÉ") and is_profane("Bâtard") and is_profane("motherfucker")
    assert not is_profane("connaissance") and not is_profane("assez")


# --------------------------------------------------------------------------- durée


def test_max_duration_is_90_seconds_everywhere(client: TestClient) -> None:
    assert MAX_CLIP_SECONDS == 90
    profiles = client.get("/api/profiles").json()
    assert all(p["max_duration"] == 90 and p["censor_profanity"] for p in profiles)
    body = {k: v for k, v in profiles[0].items() if k not in {"id", "created_at", "updated_at"}}
    r = client.put(f"/api/profiles/{profiles[0]['id']}", json=body | {"max_duration": 120})
    assert r.status_code == 422


@pytest.fixture
def fast_settings(migrated: Settings) -> Settings:
    migrated.render_x264_preset = "ultrafast"
    migrated.frames_per_candidate = 2
    return migrated


@requires_ffmpeg
def test_censored_render_and_refusal_of_long_candidates(
    client: TestClient,
    fast_settings: Settings,
    session_factory: sessionmaker[Session],
    tmp_path: Path,
) -> None:
    from tests.test_render_pipeline import SECONDS, _candidate, _profile_update, _render, _worker

    video = make_bursty_video(tmp_path / "v.mp4", SECONDS, bursts=(30, 70))
    editor = FakeEditor()
    editor.hook_text = "Quelle putain de partie"  # accroche « originale » vulgaire
    worker = _worker(fast_settings, session_factory, video, editor)
    pid, cand = _candidate(client, worker)
    assert cand["duration_seconds"] <= 90

    render = _render(client, worker, cand["id"])
    assert render["job_status"] == "completed", render["job_error"]
    assert render["plan"]["hook_text"] == "Quelle pu**** de partie"
    assert any("1 mot(s) grossier(s) masqué(s)" in w for w in render["plan"]["warnings"])
    ass = fast_settings.resolve_data_path(
        f"projects/{pid}/renders/{render['id']}/subtitles.ass"
    ).read_text(encoding="utf-8")
    assert "putain" not in ass.lower() and "pu****" in ass.lower()

    _profile_update(client, censor_profanity=False)
    raw = _render(client, worker, cand["id"])
    assert raw["plan"]["hook_text"] == "Quelle putain de partie"

    # Extrait analysé avant le passage à 90 s : refusé au montage, ignoré en lot.
    with session_factory() as s:
        s.execute(
            update(ClipCandidate)
            .where(ClipCandidate.id == cand["id"])
            .values(end_seconds=ClipCandidate.start_seconds + 125)
        )
        s.commit()
    r = client.post(f"/api/candidates/{cand['id']}/renders", json={})
    assert r.status_code == 400 and "au-delà du maximum de 90 s" in r.json()["error"]["message"]
