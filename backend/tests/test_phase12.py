"""Fin complète (chute incluse), barre de progression, séries « Partie i/N », titre percutant."""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.models import ClipCandidate
from app.render import editorial as ed
from app.render.ffmpeg_render import PROGRESS_H, filter_graph
from app.render.style import ass_inline_color
from app.render.subtitles import TITLE_HIGHLIGHT, balance_title, title_ass, title_size
from app.services.publication import build_publication
from tests.fakes import FakeEditor, make_bursty_video, requires_ffmpeg

# --------------------------------------------------------------------------- titre


def test_title_is_balanced_big_and_highlighted() -> None:
    assert balance_title("Court") == ["Court"]
    lines = balance_title("Franklin élu Employé du mois, mais à quel prix ?")
    assert len(lines) == 2 and abs(len(lines[0]) - len(lines[1])) <= 8
    assert title_size(["Court"]) == 112 and 70 <= title_size(lines) < 112
    ass = title_ass("Franklin élu Employé du mois", "Employé du mois")
    assert ass.startswith("{\\fad(120,0)\\fscx55\\fscy55\\t(0,260,\\fscx100\\fscy100)}")
    color = ass_inline_color(TITLE_HIGHLIGHT)
    assert "\\N" in ass  # deux lignes
    assert f"{{\\c{color}}}Employé" in ass and "Employé du mois" in ass.replace("\\N", " ")
    assert "{" not in title_ass("Titre {piège}")[60:]  # balises injectées neutralisées
    # Jamais de coupure à l'intérieur du mot fort (sinon il ne serait pas coloré).
    title = "Franklin élu Employé du mois, Simeon dérape !"
    assert all(
        "Employé du mois" in line or "Employé" not in line
        for line in balance_title(title, "Employé du mois")
    )
    assert rf"{{\c{color}}}Employé du mois" in title_ass(title, "Employé du mois")


def test_title_highlight_must_come_from_title() -> None:
    base = dict(
        hook_text="Le braquage tourne mal",
        hook_kind="original",
        hook_reason="",
        cta_text="",
        keywords=[],
        zooms=[],
        warnings=[],
    )
    ok = ed.validate_plan(ed.EditorialPlan(**base, title_highlight="tourne mal"), [], 70, True)
    assert ok.title_highlight == "tourne mal"
    bad = ed.validate_plan(ed.EditorialPlan(**base, title_highlight="explosion"), [], 70, True)
    assert bad.title_highlight == ""
    assert ed.validate_plan(ed.EditorialPlan(**base, extend_end=30), [], 70, True).extend_end == 10


def test_prompt_shows_following_transcript() -> None:
    after = [ed.Sentence(66.0, 68.0, "Lamar répond enfin.", [])]
    text = ed.editorial_content(None, None, [], [], 65, 0, after)[0]["text"]
    assert "Suite immédiate" in text and "Lamar répond enfin." in text  # type: ignore[operator]
    assert "extend_end" in ed.editorial_system("fr", None, "P", None)


# --------------------------------------------------------------------------- publication


def test_series_tag_in_publication() -> None:
    plan = ed.EditorialPlan(
        hook_text="Titre",
        hook_kind="original",
        hook_reason="",
        cta_text="",
        keywords=[],
        zooms=[],
        warnings=[],
    )
    pub = build_publication(
        plan=plan,
        source={"rights_status": "owned"},
        credits=[],
        candidate_summary="",
        game=None,
        series={"index": 1, "total": 2},
    )
    assert pub["youtube"]["title"].endswith("(Partie 1/2)")
    assert pub["tiktok"]["caption"].startswith("(Partie 1/2)")


# --------------------------------------------------------------------------- rendu réel


def test_progress_bar_in_graph() -> None:
    g = filter_graph(
        layout="focus",
        src_w=1920,
        src_h=1080,
        fps=30,
        zoom="1",
        ass_file="s.ass",
        duration=64,
        progress=True,
    )
    assert f"color=c=0xFFD000:s=1080x{PROGRESS_H}" in g
    assert "overlay=x='-w+w*t/64.000':y=0:eval=frame" in g


def _bar_width(video: Path, t: float) -> int:
    raw = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            str(t),
            "-i",
            str(video),
            "-frames:v",
            "1",
            "-vf",
            "crop=1080:2:0:4",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-",
        ],
        capture_output=True,
        check=True,
    ).stdout
    row = np.frombuffer(raw, dtype=np.uint8).reshape(2, 1080, 3)[0].astype(int)
    yellow = (row[:, 0] > 235) & (abs(row[:, 1] - 208) < 25) & (row[:, 2] < 60)  # #FFD000
    return int(yellow.sum())


@pytest.fixture
def fast_settings(migrated: Settings) -> Settings:
    migrated.render_x264_preset = "ultrafast"
    migrated.frames_per_candidate = 2
    return migrated


@requires_ffmpeg
def test_series_progress_and_complete_ending(
    client: TestClient,
    fast_settings: Settings,
    session_factory: sessionmaker[Session],
    tmp_path: Path,
) -> None:
    from tests.test_render_pipeline import SECONDS, _candidate, _render, _worker

    video = make_bursty_video(tmp_path / "v.mp4", SECONDS, bursts=(30, 70))
    worker = _worker(fast_settings, session_factory, video, FakeEditor())
    _, cand = _candidate(client, worker)
    # Deux extraits sélectionnés qui se suivent : le premier devient « Partie 1/2 ».
    with session_factory() as s:
        c = s.get(ClipCandidate, cand["id"])
        assert c is not None
        start, end = c.start_seconds, c.end_seconds
        s.execute(
            update(ClipCandidate)
            .where(ClipCandidate.analysis_id == c.analysis_id)
            .values(selected=False)
        )
        # Second extrait sélectionné, juste après le premier (2 s d'écart).
        s.add(
            ClipCandidate(
                analysis_id=c.analysis_id,
                position=99,
                start_seconds=end + 2,
                end_seconds=end + 70,
                status="scored",
                selected=True,
            )
        )
        c.selected = True
        s.commit()

    render = _render(client, worker, cand["id"])
    assert render["job_status"] == "completed", render["job_error"]
    assert render["plan"]["cta_text"] == "Abonne-toi pour voir la partie 2 ! 🔔"
    assert render["publication"]["youtube"]["title"].endswith("(Partie 1/2)")
    ass = fast_settings.resolve_data_path(
        f"projects/{render['project_id']}/renders/{render['id']}/subtitles.ass"
    ).read_text(encoding="utf-8")
    assert ",Badge,,0,0,0,,PARTIE 1/2" in ass
    # Fin : jamais au milieu d'une phrase (les phrases simulées durent de t à t + 4,8 s).
    rel_end = render["end_seconds"] - 1.0  # phrases à 1 + 8k
    assert (rel_end % 8) >= 4.8 or render["end_seconds"] == pytest.approx(end)
    short = fast_settings.resolve_data_path(
        f"projects/{render['project_id']}/renders/{render['id']}/short.mp4"
    )
    d = render["duration_seconds"]
    w1, w2 = _bar_width(short, d * 0.25), _bar_width(short, d * 0.75)
    assert 0.18 * 1080 < w1 < 0.32 * 1080 and 0.68 * 1080 < w2 < 0.82 * 1080, (w1, w2)
    assert start  # noqa: B018
