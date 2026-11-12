"""Titre permanent lu par la voix, bip, notation revue, confiance minimale, musique conseillée
et textes de publication."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.analysis.candidates import SelectionItem, select
from app.analysis.judge import JudgeContext, system_prompt
from app.audio import mix
from app.core.config import Settings
from app.render import editorial as ed
from app.services.publication import build_publication
from tests.fakes import FakeEditor, make_bursty_video, requires_ffmpeg

# --------------------------------------------------------------------------- sélection


def test_min_confidence_excludes_poorly_documented_ai_scores_only() -> None:
    items = [
        SelectionItem("a", 0, 70, 80, True, confidence=0.4),
        SelectionItem("b", 100, 170, 70, True, confidence=0.7),
        SelectionItem("c", 200, 270, 60, True, confidence=None),  # signaux seuls
    ]
    out = select(items, 50, min_confidence=0.5)
    assert out["a"] == (False, "Confiance de l'évaluation trop faible (0.40 < 0.50)")
    assert out["b"] == (True, None) and out["c"] == (True, None)
    assert select(items, 50)["a"] == (True, None)  # 0 par défaut : pas de filtre


def test_judge_prompt_carries_creator_rules() -> None:
    ctx = JudgeContext(
        video_title="GTA",
        creator="KVG",
        game="GTA 6",
        video_duration=600,
        profile_name="P",
        editorial_focus=None,
        language="fr",
        min_duration=61,
        max_duration=90,
    )
    prompt = system_prompt(ctx)
    assert "Ne baisse AUCUNE note pour cela" in prompt
    assert "filigrane de la chaîne source ne sont pas des défauts" in prompt
    assert "AUTRES créateurs de contenu" in prompt
    assert "transcription lacunaire" in prompt and "description de publication" in prompt


def test_profiles_have_recalibrated_defaults(client: TestClient) -> None:
    profiles = {p["name"]: p for p in client.get("/api/profiles").json()}
    assert profiles["GTA 6 — Viral"]["threshold"] == 55
    assert all(p["threshold"] == 50 for n, p in profiles.items() if n != "GTA 6 — Viral")
    assert all(
        p["min_confidence"] == 0.5 and p["music_mode"] == "suggest" for p in profiles.values()
    )
    assert all(p["narration_title"] and p["bleep_profanity"] for p in profiles.values())


# --------------------------------------------------------------------------- plan, publication


def test_editorial_prompt_title_music_and_publication() -> None:
    on = ed.editorial_system("fr", None, "P", None, music_suggest=True, publication=True)
    assert "pendant TOUTE la vidéo" in on and "aguicheur" in on
    assert "Ne cite AUCUN titre ni artiste" in on and "3 à 5" in on
    off = ed.editorial_system("fr", None, "P", None)
    assert "music_suggestion : null" in off and "publication : null" in off


def test_publication_adds_credits_cleans_hashtags_and_censors() -> None:
    plan = ed.EditorialPlan(
        hook_text="Le braquage tourne mal",
        hook_kind="original",
        hook_reason="",
        cta_text="",
        keywords=[],
        zooms=[],
        warnings=[],
        publication=ed.Publication(
            context="Franklin et Lamar volent une voiture.",
            question="Putain, t'aurais fait quoi ?",
            tiktok_caption="Ça part en vrille 😳",
            youtube_title="Le vol qui tourne mal",
            hashtags=["gta6", "#GTA6", "#gaming", "#open world", "#a", "#b", "#c"],
        ),
    )
    pub = build_publication(
        plan=plan,
        source={
            "title": "GTA V",
            "uploader": "KVG",
            "url": "https://y/v",
            "rights_status": "unknown",
        },
        credits=[{"kind": "voice", "text": "Voix SIWIS — CC BY 4.0"}],
        candidate_summary=None,
        game="GTA 6",
    )
    assert pub["hashtags"] == ["#gta6", "#gaming", "#openworld", "#a", "#b"]
    assert pub["credits"] == ["Source : « GTA V » — KVG (https://y/v)", "Voix SIWIS — CC BY 4.0"]
    desc = pub["youtube"]["description"]
    assert desc.startswith("Franklin et Lamar") and "KVG" in desc and "CC BY" in desc
    assert "Pu****, t'aurais" in desc and "Putain" not in pub["tiktok"]["caption"]
    assert pub["generated_by_ai"] and pub["music_suggestion"] is None

    plan.publication = None  # plan sans IA
    fallback = build_publication(
        plan=plan,
        source={"rights_status": "owned"},
        credits=[],
        candidate_summary="Résumé.",
        game="GTA 6",
    )
    assert not fallback["generated_by_ai"] and fallback["credits"] == []
    assert (
        "#gta6" in fallback["hashtags"] and fallback["youtube"]["title"] == "Le braquage tourne mal"
    )


# --------------------------------------------------------------------------- bip


def test_beep_track() -> None:
    track = mix.beep_track([(1.0, 1.3)], 3 * mix.SR)
    assert (
        np.abs(track[:, : mix.SR]).max() == 0
        and np.abs(track[:, int(1.3 * mix.SR) + 10 :]).max() == 0
    )
    mid = track[0, int(1.1 * mix.SR) : int(1.2 * mix.SR)]
    assert 0.24 < np.abs(mid).max() <= 0.25
    # 1 kHz : 100 passages par zéro dans 0,1 s (à quelques près)
    assert 190 <= int(np.sum(np.diff(np.sign(mid)) != 0)) <= 202


# --------------------------------------------------------------------------- rendu réel


@pytest.fixture
def fast_settings(migrated: Settings) -> Settings:
    migrated.render_x264_preset = "ultrafast"
    migrated.frames_per_candidate = 2
    return migrated


@requires_ffmpeg
def test_render_reads_title_keeps_it_on_screen_and_prepares_publication(
    client: TestClient,
    fast_settings: Settings,
    session_factory: sessionmaker[Session],
    tmp_path: Path,
) -> None:
    from tests.test_phase5_pipeline import FakeToolkit
    from tests.test_phase5_pipeline import _worker as worker5
    from tests.test_render_pipeline import SECONDS, _candidate, _profile_update, _render

    _profile_update(client, source_music_mode="off")
    video = make_bursty_video(tmp_path / "v.mp4", SECONDS, bursts=(30, 70))
    toolkit = FakeToolkit()
    worker = worker5(fast_settings, session_factory, video, FakeEditor(), toolkit)
    pid, cand = _candidate(client, worker)
    render = _render(client, worker, cand["id"])
    assert render["job_status"] == "completed", render["job_error"]

    narr = render["audio_report"]["narration"]
    assert narr["status"] == "added" and narr["title"]["text"] == "Une partie qui démarre fort"
    assert toolkit.tts_engine.texts[0] == "Une partie qui démarre fort"
    # Le titre n'est pas sous-titré (il est déjà affiché) ; il reste à l'écran jusqu'à la fin.
    assert not any(c["text"].startswith("Une partie") for c in render["subtitles"])
    ass = fast_settings.resolve_data_path(
        f"projects/{pid}/renders/{render['id']}/subtitles.ass"
    ).read_text(encoding="utf-8")
    end = f"{int(render['duration_seconds'] // 60)}:{render['duration_seconds'] % 60:05.2f}"
    assert "Hook,,0,0,0,,{\\fad(150,0)}Une partie qui démarre fort" in ass
    assert f",0:0{end}," in ass or end in ass
    assert render["audio_report"]["bleep"] == {"enabled": True, "count": 0, "times": []}
    assert render["audio_report"]["music"]["status"] == "disabled"  # conseillée, pas incrustée

    pub = render["publication"]
    assert pub["music_suggestion"]["search_keywords"] == ["dark trap", "tense"]
    assert "bibliothèque sonore" in pub["music_suggestion"]["note"]
    assert pub["hashtags"] == ["#gta6", "#gaming", "#Shortsgame"]
    assert any(c.startswith("Source :") for c in pub["credits"])
    assert any("SIWIS" in c for c in pub["credits"])  # la voix a lu le titre : crédit CC BY
    assert pub["youtube"]["title"] == "Une partie qui démarre fort"
