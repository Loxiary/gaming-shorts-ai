"""Rétention : gros plan qui suit le visage, sous-titres traduits animés, rythme, ouverture."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.render import editorial as ed
from app.render.facecam import Face
from app.render.ffmpeg_render import FOCUS_TOP, filter_graph, zoom_expression
from app.render.focus import MAX_PAN_PER_S, center_expression, focus_track
from app.render.subtitles import POP, build_ass, cues_from_translation
from app.workers.pipeline.render import jump_times
from tests.fakes import FakeEditor, make_bursty_video, requires_ffmpeg

# --------------------------------------------------------------------------- gros plan


def _face(cx: float, w: float = 0.1, score: float = 0.9) -> Face:
    return Face(cx - w / 2, 0.3, w, w * 1.6, score)


def test_focus_track_follows_largest_face_smoothly() -> None:
    samples = [
        (0.0, []),  # pas de visage au début : on prendra le premier trouvé
        (1.5, [_face(0.30), _face(0.8, w=0.05)]),  # le plus grand gagne
        (3.0, [_face(0.32)]),
        (4.5, [_face(0.95, w=0.02)]),  # trop petit : ignoré, position gardée
        (6.0, [_face(0.70)]),  # changement de personnage : panoramique limité
        (7.5, [_face(0.70)]),
    ]
    track = focus_track(samples)
    xs = [x for _, x in track]
    assert xs[0] == pytest.approx(0.30) and xs[2] == pytest.approx(0.32, abs=0.01)
    for (t0, x0), (t1, x1) in zip(track, track[1:], strict=False):
        assert abs(x1 - x0) <= MAX_PAN_PER_S * (t1 - t0) + 1e-6
    assert focus_track([(0.0, []), (1.5, [])]) == []
    # Le visage du facecam de la source (zone exclue) n'attire jamais le cadre.
    excluded = focus_track([(0.0, [_face(0.9), _face(0.4)])], exclude=[0.8, 0.0, 0.2, 1.0])
    assert excluded == [(0.0, pytest.approx(0.4))]


def test_center_expression_and_focus_layout() -> None:
    assert center_expression([]) == "0.5"
    expr = center_expression([(0.0, 0.3), (2.0, 0.5)])
    assert "between(t,0.00,2.00-0.001)*(0.3000+0.10000*(t-0.00))" in expr
    g = filter_graph(
        layout="focus",
        src_w=1920,
        src_h=1080,
        fps=30,
        zoom="1",
        ass_file="s.ass",
        duration=60,
        focus=expr,
    )
    assert "crop=w='min(iw,ih)':h='min(iw,ih)':x='max(0,min(iw-min(iw,ih),iw*(" in g
    assert f"overlay=x=0:y={FOCUS_TOP}" in g and "scale=1080:1080" in g


# --------------------------------------------------------------------------- rythme


def test_jump_times_and_zoom_expression() -> None:
    assert jump_times([0.5, 2.0, 4.0, 5.0, 8.0, 11.9, 59.5], 60) == [4.0, 8.0, 11.9]
    z = zoom_expression([], 0.12, jumps=[4.0, 8.0], duration=20)
    assert "0.12*(between(t,4.000,8.000-0.001)" in z  # un plan sur deux resserré
    assert "between(t,8.000" not in z and "0.04*t/20.000" in z


# --------------------------------------------------------------------------- sous-titres


def test_translated_subtitles_are_animated_word_by_word() -> None:
    s = ed.Sentence(1.0, 3.0, "Hello there friend", [])
    cues = cues_from_translation([s], ["Salut mon ami"], 3, 10)
    assert len(cues) == 1 and cues[0].karaoke
    words = cues[0].words
    assert [w for _, _, w in words] == ["Salut", "mon", "ami"]
    assert words[0][0] == 1.0 and words[-1][1] == pytest.approx(3.0)
    assert words[0][1] - words[0][0] > words[1][1] - words[1][0]  # mot plus long = plus de temps
    style = {
        "font": "Arial",
        "size": 70,
        "text_color": "#FFFFFF",
        "highlight_color": "#FFFF00",
        "keyword_color": "#00FFFF",
        "uppercase": True,
        "max_words": 3,
    }
    ass = build_ass(
        cues=cues, style=style, keywords=["ami"], hook=None, cta=None, duration=10, layout="focus"
    )
    lines = [x for x in ass.splitlines() if x.startswith("Dialogue: 0")]
    assert len(lines) == 3 and lines[0].count(POP) == 1 and POP not in lines[1]


def test_translation_schema_and_prompt_have_keywords() -> None:
    assert ed.Translation(sentences=[]).keywords == []
    assert "keywords" in ed.translation_system("en", "fr")


# --------------------------------------------------------------------------- ouverture


def test_trim_prompt_and_bounds() -> None:
    assert "trim_start" in ed.editorial_system("fr", None, "P", None)
    plan = ed.EditorialPlan(
        hook_text="T",
        hook_kind="original",
        hook_reason="",
        cta_text="",
        keywords=[],
        zooms=[],
        warnings=[],
        trim_start=40,
    )
    assert ed.validate_plan(plan, [], 70, True).trim_start == ed.MAX_TRIM_START


@pytest.fixture
def fast_settings(migrated: Settings) -> Settings:
    migrated.render_x264_preset = "ultrafast"
    migrated.frames_per_candidate = 2
    return migrated


@requires_ffmpeg
def test_render_trims_slow_opening_and_extends_end(
    client: TestClient,
    fast_settings: Settings,
    session_factory: sessionmaker[Session],
    tmp_path: Path,
) -> None:
    from tests.test_render_pipeline import SECONDS, _candidate, _render, _worker

    video = make_bursty_video(tmp_path / "v.mp4", SECONDS, bursts=(30, 70))
    editor = FakeEditor()
    editor.trim_start = 8.5  # phrases toutes les 8 s : se cale sur le début de phrase à 9 s
    worker = _worker(fast_settings, session_factory, video, editor)
    _, cand = _candidate(client, worker)
    render = _render(client, worker, cand["id"])
    assert render["job_status"] == "completed", render["job_error"]
    shift = render["start_seconds"] - cand["start_seconds"]
    assert shift > 0 and render["plan"]["trim_start"] == pytest.approx(shift, abs=0.01)
    assert 61 <= render["duration_seconds"] <= 90 and render["qc_passed"]
    assert render["end_seconds"] > cand["end_seconds"]  # fin prolongée
    assert any(w.startswith("Ouverture directe") for w in render["plan"]["warnings"])
    # Les zooms du plan suivent le décalage (10 s dans l'extrait d'origine → 10 - décalage).
    assert render["plan"]["zooms"][0]["t"] == pytest.approx(10 - shift, abs=0.01)
