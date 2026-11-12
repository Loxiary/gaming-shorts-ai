"""Tests unitaires de la Phase 4 : styles, sous-titres ASS, plan éditorial, risques."""

from __future__ import annotations

import pytest

from app.render import editorial as ed
from app.render.ffmpeg_render import zoom_expression
from app.render.risk import build_risk_report, export_warnings
from app.render.style import ass_color, ass_inline_color, normalize_subtitle_style
from app.render.subtitles import build_ass, cues_from_translation, cues_from_words


def _sentences() -> list[ed.Sentence]:
    words1 = [
        (0.5, 0.9, "Attention,"),
        (1.0, 1.3, "il"),
        (1.3, 1.7, "arrive"),
        (1.7, 2.2, "maintenant!"),
    ]
    words2 = [
        (3.5, 3.9, "On"),
        (3.9, 4.2, "a"),
        (4.2, 4.8, "gagné"),
        (4.8, 5.4, "3000"),
        (5.4, 6.0, "dollars."),
    ]
    return [
        ed.Sentence(0.5, 2.2, "Attention, il arrive maintenant!", words1),
        ed.Sentence(3.5, 6.0, "On a gagné 3000 dollars.", words2),
    ]


def test_style_validation_and_colors() -> None:
    style = normalize_subtitle_style({"font": "Impact", "size": 90, "highlight_color": "#ff0000"})
    assert style["font"] == "Impact" and style["highlight_color"] == "#FF0000"
    assert style["max_words"] == 3 and style["uppercase"] is True
    for bad in ({"font": "Comic Sans"}, {"size": 200}, {"text_color": "red"}, {"max_words": 9}):
        with pytest.raises(ValueError):
            normalize_subtitle_style(bad)
    assert ass_color("#FFE500") == "&H0000E5FF"
    assert ass_inline_color("#38E1FF") == "&HFFE138&"


def test_cues_group_words_and_break_on_sentences_and_gaps() -> None:
    words = [w for s in _sentences() for w in s.words]
    cues = cues_from_words(words, max_words=3, duration=70)
    texts = [c.text for c in cues]
    assert texts == ["Attention, il arrive", "maintenant!", "On a gagné", "3000 dollars."]
    assert all(c.end > c.start for c in cues)
    assert cues[1].end <= cues[2].start  # pas de chevauchement entre groupes


def test_translation_cues_follow_sentence_timing() -> None:
    sentences = _sentences()
    cues = cues_from_translation(
        sentences, ["Careful, he's coming now!", "We won 3000 dollars."], max_words=3, duration=70
    )
    assert cues[0].start == pytest.approx(0.5) and not cues[0].karaoke
    first_sentence = [c for c in cues if c.start < 3]
    assert first_sentence[-1].end == pytest.approx(2.2)


def test_ass_escapes_text_and_places_hook_and_cta() -> None:
    style = normalize_subtitle_style({})
    words = [(0.5, 1.0, "{\\pos(0,0)}piège"), (1.0, 1.5, "3000")]
    cues = cues_from_words(words, 3, 70)
    ass = build_ass(
        cues=cues,
        style=style,
        keywords=["3000"],
        hook="Accroche {test}",
        cta="Abonne-toi !",
        duration=70,
        layout="blur",
    )
    assert "\\pos" not in ass  # aucune balise injectée depuis le texte
    assert "Accroche (test)" in ass
    assert "Dialogue: 2,0:00:00.00,0:01:10.00,Hook" in ass
    assert "Dialogue: 2,0:01:06.00,0:01:10.00,Cta" in ass
    assert "PlayResX: 1080" in ass and "PlayResY: 1920" in ass
    assert "{\\c&HFFE138&}3000" in ass  # mot clé en couleur


def test_plan_validation_rules() -> None:
    sentences = _sentences()

    def plan(**kw: object) -> ed.EditorialPlan:
        base = {
            "hook_text": "On a gagné 3000 dollars",
            "hook_kind": "quote",
            "hook_reason": "x",
            "cta_text": "Abonne-toi !",
            "keywords": ["3000"],
            "zooms": [],
            "warnings": [],
        }
        return ed.EditorialPlan.model_validate(base | kw)

    ed.validate_plan(plan(), sentences, 70, True)
    with pytest.raises(ValueError, match="réellement prononcée"):
        ed.validate_plan(plan(hook_text="Il a perdu un million"), sentences, 70, True)
    ed.validate_plan(
        plan(hook_text="Une victoire inattendue", hook_kind="original"), sentences, 70, True
    )
    with pytest.raises(ValueError, match="caractères"):
        ed.validate_plan(plan(hook_text="x" * 80, hook_kind="original"), sentences, 70, True)
    with pytest.raises(ValueError, match="zoom"):
        ed.validate_plan(
            plan(zooms=[{"t": 69, "duration": 3, "reason": "fin"}]), sentences, 70, True
        )
    assert ed.filter_keywords(["3000", "absent", "Gagné!"], ["On", "a", "gagné", "3000"]) == [
        "3000",
        "gagné",
    ]


def test_fallback_plan_uses_real_quote_and_peaks() -> None:
    plan = ed.fallback_plan(
        _sentences(),
        peaks=[4.0, 40.0],
        duration=70,
        hook_enabled=True,
        cta_text=None,
        language="fr",
    )
    assert plan.hook_text == "On a gagné 3000 dollars."
    assert plan.cta_text == "Abonne-toi pour la suite !"
    assert [z.t for z in plan.zooms] == [3.5, 39.5]
    assert "3000" in plan.keywords
    assert any("sans IA" in w for w in plan.warnings)


def test_zoom_expression() -> None:
    assert zoom_expression([], 0.12) == "1"
    zooms = [ed.ZoomMoment(t=2, duration=1.5, reason="x")]
    assert zoom_expression(zooms, 0) == "1"
    assert zoom_expression(zooms, 0.12).startswith("1+0.120*(between(t,2.000,3.500)")


def _report(rights: str, **plan_kw: object) -> dict:
    plan = {
        "hook_text": "Accroche",
        "cta_text": "Abonne-toi",
        "zooms": [1],
        "hook_kind": "quote",
        "warnings": [],
    } | plan_kw
    return build_risk_report(
        source={
            "title": "Partie",
            "uploader": "Créateur",
            "url": "https://y/v",
            "rights_status": rights,
        },
        profile={"name": "Viral"},
        plan=plan,
        plan_engine="llm",
        subtitles_translated=False,
        subtitles_enabled=True,
        candidate={"warnings": ["Musique possible"]},
        qc={"checks": [{"ok": False, "label": "Volume", "detail": "-20 LUFS", "level": "warning"}]},
    )


def test_risk_report_is_informative_and_never_blocking() -> None:
    unknown = _report("unknown")
    assert unknown["blocking"] is False
    assert unknown["reused_content"]["level"] == "élevé"
    assert unknown["rights"]["verified_by_app"] is False
    assert unknown["audio_music"]["status"] == "non_analysée"
    assert unknown["transformation"]["level"] == "modérée"
    assert any("Créditez" in r for r in unknown["recommendations"])
    assert "Musique possible" in unknown["ai_warnings"]
    warnings = export_warnings(unknown, None)
    assert "Droits sur la source non vérifiés." in warnings
    assert "Volume : -20 LUFS" in warnings

    owned = _report("owned", hook_kind="original")
    assert owned["reused_content"]["level"] == "faible"
    assert not any("Créditez" in r for r in owned["recommendations"])
    assert any(w.startswith("Accroche originale") for w in export_warnings(owned, None))


def test_event_times_are_normalized_absolute_or_relative() -> None:
    from app.analysis.judge import event_time_absolute

    assert event_time_absolute(120.0, 94.7, 173.1) == 120.0  # déjà absolu
    assert event_time_absolute(21.3, 94.7, 173.1) == pytest.approx(116.0)  # relatif -> absolu
    content = ed.editorial_content(
        "Résumé",
        "Raison",
        [{"t": 21.3, "description": "Explosion"}, {"t": 120.0, "description": "Centrale"}],
        _sentences(),
        duration=78.4,
        offset=94.7,
    )[0]["text"]
    assert "- 0:21 : Explosion" in content and "- 0:25 : Centrale" in content
