"""Phase 7 : transitions et effets ponctuels (plan, filtres FFmpeg, bruitages, rendu réel)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.audio import sfx
from app.core.config import Settings
from app.render import editorial as ed
from app.render.ffmpeg_render import effects_chain, filter_graph, zoom_expression
from app.render.risk import build_risk_report
from tests.fakes import FakeEditor, make_bursty_video, requires_ffmpeg

FX = ed.EffectMoment


def _plan(**kw: object) -> ed.EditorialPlan:
    base = dict(
        hook_text="Ça part",
        hook_kind="original",
        hook_reason="",
        cta_text="",
        keywords=[],
        zooms=[],
        warnings=[],
    )
    return ed.EditorialPlan(**(base | kw))  # type: ignore[arg-type]


# --------------------------------------------------------------------------- plan


def test_effects_are_validated_against_overload() -> None:
    ok = [
        FX(t=5, kind="flash", duration=0.3, reason="r"),
        FX(t=8, kind="shake", duration=0.6, reason="r"),
    ]
    assert len(ed.validate_plan(_plan(effects=ok), [], 60, True).effects) == 2
    cases = {
        "plus de 4 effets": [
            FX(t=3 + 3 * i, kind="flash", duration=0.2, reason="") for i in range(5)
        ],
        "moins de 2.5 s": [
            FX(t=5, kind="flash", duration=0.2, reason=""),
            FX(t=6, kind="shake", duration=0.5, reason=""),
        ],
        "hors de l'extrait": [FX(t=59.8, kind="flash", duration=0.2, reason="")],
        "durée 3 s": [FX(t=5, kind="shake", duration=3, reason="")],
    }
    for message, effects in cases.items():
        plan = ed.validate_plan(_plan(effects=effects), [], 60, True)  # jamais d'exception
        assert len(plan.effects) == len(effects) - 1 if len(effects) > 1 else not plan.effects
        assert any(message in w for w in plan.warnings), (message, plan.warnings)
    legacy = _plan().model_dump()
    legacy.pop("effects")
    assert ed.EditorialPlan.model_validate(legacy).effects == []


def test_prompt_asks_for_rare_justified_effects_only_when_enabled() -> None:
    on = ed.editorial_system("fr", None, "P", None, effects=True)
    assert "aucun effet" in on and "« shake »" in on and "2.5 s" in on
    assert "9. effects : liste vide." in ed.editorial_system("fr", None, "P", None)


# --------------------------------------------------------------------------- filtres


def test_effects_chain_and_transitions() -> None:
    assert effects_chain([], 60, "none", "none") == ""
    chain = effects_chain(
        [
            FX(t=5, kind="flash", duration=0.3, reason=""),
            FX(t=9, kind="shake", duration=0.6, reason=""),
        ],
        60,
        "fade",
        "fade",
    )
    assert chain.startswith("scale=1124:1996,crop=1080:1920")  # marge du tremblement
    assert "eq=brightness='0.6*(between(t,5.000,5.300)" in chain
    assert "fade=t=in:st=0:d=0.4" in chain and "fade=t=out:st=59.400:d=0.6" in chain
    assert zoom_expression([], 0.12) == "1"
    assert "pow(max(0,1-t/0.6),2)" in zoom_expression([], 0.12, intro_zoom=True)
    g = filter_graph(
        layout="fill",
        src_w=1920,
        src_h=1080,
        fps=30,
        zoom="1",
        ass_file="s.ass",
        duration=60,
        effects=chain,
    )
    # Effets avant les textes : l'accroche et les sous-titres restent nets et lisibles.
    assert g.index("eq=brightness") < g.index("ass=s.ass")


# --------------------------------------------------------------------------- bruitages


def test_synthesized_sfx_are_deterministic_and_placed() -> None:
    w, i = sfx.whoosh(), sfx.impact()
    assert w.shape == (2, int(0.6 * sfx.SR)) and i.shape == (2, int(0.5 * sfx.SR))
    assert np.array_equal(w, sfx.whoosh())  # même graine, même son
    assert 0.7 < np.max(np.abs(w)) <= 0.81 and 0.85 < np.max(np.abs(i)) <= 0.91
    # Impact : énergie concentrée au début ; souffle : maximum au milieu.
    q = len(i[0]) // 4
    assert np.abs(i[0, :q]).mean() > 5 * np.abs(i[0, -q:]).mean()
    env = np.abs(w[0]).reshape(-1, 1323).mean(axis=1)
    assert 5 <= int(np.argmax(env)) <= 15
    track, placed = sfx.build_track([(2.0, "impact"), (5.0, "whoosh")], 10 * sfx.SR)
    assert placed == [{"t": 2.0, "kind": "impact"}, {"t": 5.0, "kind": "whoosh"}]
    assert np.abs(track[:, : int(1.9 * sfx.SR)]).max() == 0
    assert np.abs(track[:, int(2.0 * sfx.SR) : int(2.1 * sfx.SR)]).max() > 0.3


def test_risk_report_counts_effects_and_transitions() -> None:
    r = build_risk_report(
        source={"rights_status": "unknown"},
        profile={"name": "P", "transition_in": "zoom", "transition_out": "fade"},
        plan={"hook_text": "h", "effects": [{"t": 5}, {"t": 9}]},
        plan_engine="llm",
        subtitles_translated=False,
        subtitles_enabled=True,
        candidate=None,
        qc=None,
    )
    assert "2 effet(s) ponctuel(s)" in r["transformation"]["added"]
    assert "transitions" in r["transformation"]["added"]


# --------------------------------------------------------------------------- rendu réel


@pytest.fixture
def fast_settings(migrated: Settings) -> Settings:
    migrated.render_x264_preset = "ultrafast"
    migrated.frames_per_candidate = 2
    return migrated


@requires_ffmpeg
def test_render_with_effects_transitions_and_sfx(
    client: TestClient,
    fast_settings: Settings,
    session_factory: sessionmaker[Session],
    tmp_path: Path,
) -> None:
    from tests.test_phase5_pipeline import FakeToolkit
    from tests.test_phase5_pipeline import _worker as worker5
    from tests.test_render_pipeline import SECONDS, _candidate, _profile_update, _render

    _profile_update(
        client,
        transition_in="zoom",
        transition_out="fade",
        sfx_level_db=-10,
        source_music_mode="off",
        music_mode="off",
        narration_mode="off",
    )
    video = make_bursty_video(tmp_path / "v.mp4", SECONDS, bursts=(30, 70))
    editor = FakeEditor(effects=[(6.0, "flash", 0.3), (12.0, "shake", 0.6)])
    worker = worker5(fast_settings, session_factory, video, editor, FakeToolkit())
    pid, cand = _candidate(client, worker)
    render = _render(client, worker, cand["id"])
    assert render["job_status"] == "completed", render["job_error"]
    assert "« flash »" in editor.systems[-1]
    assert [e["kind"] for e in render["plan"]["effects"]] == ["flash", "shake"]
    s = render["audio_report"]["sfx"]
    assert s["status"] == "added" and s["synthetic"] is True
    assert [e["kind"] for e in s["events"]] == ["whoosh", "whoosh", "impact"]
    assert render["qc_passed"] is True
    assert "2 effet(s) ponctuel(s)" in render["risk_report"]["transformation"]["added"]

    # Le flash éclaircit réellement l'image à t = 6 s ; le fondu de sortie l'assombrit.
    short = fast_settings.resolve_data_path(f"projects/{pid}/renders/{render['id']}/short.mp4")

    def luma(t: float) -> float:
        out = subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-ss",
                str(t),
                "-i",
                str(short),
                "-frames:v",
                "1",
                "-vf",
                "signalstats,metadata=print:key=lavfi.signalstats.YAVG",
                "-f",
                "null",
                "-",
            ],
            capture_output=True,
            text=True,
            check=True,
        ).stderr
        return float(next(x for x in out.splitlines() if "YAVG" in x).split("=")[1])

    assert luma(6.03) > luma(8.0) + 40
    assert luma(render["duration_seconds"] - 0.25) < luma(8.0) - 30

    # Effets désactivés dans le profil : aucun effet, même si l'IA en propose.
    _profile_update(
        client, effects_mode="off", sfx_mode="off", transition_in="none", transition_out="none"
    )
    second = _render(client, worker, cand["id"])
    assert second["job_status"] == "completed", second["job_error"]
    assert second["plan"]["effects"] == []
    assert second["audio_report"]["sfx"]["status"] == "disabled"
    assert "« flash »" not in editor.systems[-1]


def test_whisper_subword_tokens_are_glued_in_subtitles() -> None:
    from app.workers.pipeline.render import is_continuation

    assert is_continuation(",000") and is_continuation("-minute") and is_continuation("'s")
    assert not is_continuation(" 4") and not is_continuation(" ,000") and not is_continuation("")
    assert not is_continuation("Hello")  # premier mot d'un segment sans espace : jamais recollé
