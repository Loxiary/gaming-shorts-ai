"""Engagement : rappel en cours de vidéo, questions à choix, commentaire à épingler, réactions."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.render import editorial as ed
from app.render.ffmpeg_render import react_center
from app.render.style import normalize_subtitle_style
from app.render.subtitles import REACTION_LABELS, build_ass
from tests.fakes import FakeEditor, make_bursty_video, requires_ffmpeg

R = ed.ReactionMoment


def _plan(**kw: object) -> ed.EditorialPlan:
    base = dict(
        hook_text="T",
        hook_kind="original",
        hook_reason="",
        cta_text="",
        keywords=[],
        zooms=[],
        warnings=[],
    )
    return ed.EditorialPlan(**(base | kw))  # type: ignore[arg-type]


def test_reactions_are_rare_and_mid_cta_is_mid_video() -> None:
    plan = ed.validate_plan(
        _plan(
            reactions=[
                R(t=0.2, kind="laugh"),
                R(t=5, kind="shock"),
                R(t=7, kind="fail"),
                *(R(t=10 + 5 * i, kind="hype") for i in range(6)),
            ],
            mid_cta_text="👍 si Simeon est le pire boss " * 3,
            mid_cta_t=2,
        ),
        [],
        70,
        True,
    )
    assert [r.t for r in plan.reactions] == [5, 10, 15, 20, 25]
    assert sum("écartée" in w for w in plan.warnings) == 4  # 0,2 s ; 7 s ; 30 s ; 35 s
    assert len(plan.mid_cta_text) == ed.MAX_MID_CTA_CHARS
    assert plan.mid_cta_t == pytest.approx(70 * 0.45)


def test_prompt_asks_for_closed_questions_reactions_and_pinned_comment() -> None:
    p = ed.editorial_system("fr", None, "P", None, publication=True)
    assert "question FERMÉE à choix" in p and "Team Franklin ou Team Lamar" in p
    assert "pinned_comment" in p and "mid_cta_text" in p and "reactions" in p


def test_ass_has_mid_cta_reaction_stickers_and_big_final_cta() -> None:
    ass = build_ass(
        cues=[],
        style=normalize_subtitle_style(None),
        keywords=[],
        hook=None,
        cta="Team Franklin ou Team Lamar ?",
        duration=70,
        layout="focus",
        mid_cta=(30.0, "👍 si Simeon est le pire boss"),
        reactions=[(12.0, REACTION_LABELS["fr"]["laugh"])],
        reaction_anchor=(680, 780),
    )
    assert "Style: Cta,Arial Black,70," in ass
    assert r"Dialogue: 2,0:00:30.00,0:00:33.50,Cta,,0,0,0,,{\fad(150,0)" in ass
    assert "👍 si Simeon est le pire boss" in ass
    sticker = next(x for x in ass.splitlines() if ",React," in x)
    assert sticker.startswith("Dialogue: 4,0:00:12.00,0:00:13.30,React")
    assert r"\pos(680,780)\frz-12" in sticker and sticker.endswith("MDR 😂")


def test_reaction_anchor_sits_next_to_the_react_circle() -> None:
    cx, cy = react_center("focus", 1920, 1080, 360)
    assert (cx, cy) == (1080 - 40 - 189, 420 + 189)


@pytest.fixture
def fast_settings(migrated: Settings) -> Settings:
    migrated.render_x264_preset = "ultrafast"
    migrated.frames_per_candidate = 2
    return migrated


@requires_ffmpeg
def test_render_with_reactions_mid_cta_and_pinned_comment(
    client: TestClient,
    fast_settings: Settings,
    session_factory: sessionmaker[Session],
    tmp_path: Path,
) -> None:
    from tests.test_render_pipeline import SECONDS, _candidate, _profile_update, _render, _worker

    video = make_bursty_video(tmp_path / "v.mp4", SECONDS, bursts=(30, 70))
    editor = FakeEditor()
    editor.reactions = [(8.0, "laugh"), (20.0, "shock")]
    editor.mid_cta_text = "👍 si la partie démarre fort"
    worker = _worker(fast_settings, session_factory, video, editor)
    pid, cand = _candidate(client, worker)
    render = _render(client, worker, cand["id"])
    assert render["job_status"] == "completed", render["job_error"]
    assert render["publication"]["pinned_comment"] == "Team Franklin ou Team Lamar ? 👇"
    ass = fast_settings.resolve_data_path(
        f"projects/{pid}/renders/{render['id']}/subtitles.ass"
    ).read_text(encoding="utf-8")
    assert sum(",React," in x for x in ass.splitlines() if x.startswith("Dialogue")) == 2
    assert "QUOI ?! 😳" in ass and "👍 si la partie démarre fort" in ass

    _profile_update(client, mid_cta=False, reactions=False)
    off = _render(client, worker, cand["id"])
    ass = fast_settings.resolve_data_path(
        f"projects/{pid}/renders/{off['id']}/subtitles.ass"
    ).read_text(encoding="utf-8")
    assert ",React," not in "".join(x for x in ass.splitlines() if x.startswith("Dialogue"))
    assert "👍 si la partie démarre fort" not in ass


def _count(schema: object) -> tuple[int, int]:
    """(champs optionnels, unions) dans un schéma JSON."""
    opt = uni = 0
    if isinstance(schema, dict):
        if "properties" in schema:
            opt += len(set(schema["properties"]) - set(schema.get("required", [])))
        uni += "anyOf" in schema
        for v in schema.values():
            o, u = _count(v)
            opt, uni = opt + o, uni + u
    elif isinstance(schema, list):
        for v in schema:
            o, u = _count(v)
            opt, uni = opt + o, uni + u
    return opt, uni


def test_llm_schema_stays_simple_enough_for_structured_outputs() -> None:
    """Régression : l'API a refusé le plan (« Schema is too complex ») avec 16 champs
    optionnels et 2 unions. Le schéma envoyé à l'IA n'en a aucun."""
    assert _count(ed.EditorialPlanLLM.model_json_schema()) == (0, 0)


def test_from_llm_drops_unknown_kinds_and_empty_blocks() -> None:
    llm = ed.EditorialPlanLLM(
        hook_text="T",
        hook_kind="original",
        hook_reason="",
        title_highlight="",
        cta_text="",
        mid_cta_text="",
        mid_cta_t=0,
        keywords=[],
        zooms=[],
        effects=[
            ed.EffectLLM(t=5, kind="flash", duration=0.3, reason=""),
            ed.EffectLLM(t=9, kind="explosion", duration=1, reason=""),
        ],
        reactions=[ed.ReactionLLM(t=5, kind="laugh"), ed.ReactionLLM(t=12, kind="cry")],
        narration_needed=False,
        narration_reason="",
        narration=[],
        music_mood="",
        music_suggestion=ed.MusicLLM(mood="", genre="", tempo="", search_keywords=[], why=""),
        publication=ed.PublicationLLM(
            context="",
            question="",
            pinned_comment="",
            tiktok_caption="",
            youtube_title="",
            hashtags=[],
        ),
        trim_start=0,
        trim_reason="",
        extend_end=0,
        extend_reason="",
        warnings=[],
    )
    plan = ed.from_llm(llm)
    assert [e.kind for e in plan.effects] == ["flash"]
    assert [r.kind for r in plan.reactions] == ["laugh"]
    assert plan.music_suggestion is None and plan.publication is None
