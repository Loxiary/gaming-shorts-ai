"""Phase 5 : décisions facecam, mixage (ducking, placement de la narration), plan, risques."""

from __future__ import annotations

import numpy as np
import pytest

from app.audio import mix
from app.render import editorial as ed
from app.render.facecam import Face, analyze_detections
from app.render.ffmpeg_render import filter_graph
from app.render.risk import build_risk_report, export_warnings

CORNER = Face(0.82, 0.70, 0.08, 0.14, 0.95)  # visage en bas à droite


# --------------------------------------------------------------------------- facecam


def test_persistent_corner_face_is_cropped_out_on_the_cheapest_side() -> None:
    frames = [[CORNER] for _ in range(9)] + [[]]
    r = analyze_detections(frames)
    assert r["status"] == "detected" and r["presence"] == 0.9
    x, y, w, h = r["crop"]
    assert r["crop_side"] == "droite"
    assert (x, y, h) == (0.0, 0.0, 1.0)
    # La zone gardée s'arrête avant le cadre estimé de la webcam (qui contient le visage).
    assert w <= CORNER.x and r["loss"] == pytest.approx(1 - w)
    assert r["warning"] is None


def test_no_face_or_moving_faces_are_not_a_facecam() -> None:
    assert analyze_detections([[] for _ in range(10)])["status"] == "none"
    moving = [[Face(0.1 * i, 0.4, 0.06, 0.1, 0.9)] for i in range(10)]
    assert analyze_detections(moving)["status"] == "none"
    weak = [[Face(0.82, 0.7, 0.08, 0.14, 0.5)] for _ in range(10)]  # score trop faible
    assert analyze_detections(weak)["status"] == "none"


def test_uncertain_cases_are_reported_without_cropping() -> None:
    sometimes = [[CORNER] if i < 3 else [] for i in range(10)]
    r = analyze_detections(sometimes)
    assert r["status"] == "uncertain" and r["crop"] is None and "30%" in r["warning"]
    central = [[Face(0.45, 0.4, 0.1, 0.18, 0.95)] for _ in range(10)]
    r = analyze_detections(central)
    assert r["status"] == "uncertain" and "centre" in r["warning"]
    assert analyze_detections([])["status"] == "unavailable"


def test_large_crop_loss_triggers_a_warning() -> None:
    big = Face(0.62, 0.55, 0.16, 0.3, 0.95)
    r = analyze_detections([[big] for _ in range(10)])
    assert r["status"] == "detected" and r["loss"] > 0.35
    assert "vérifiez" in r["warning"]


def test_filter_graph_applies_crop_and_uses_mixed_audio() -> None:
    g = filter_graph(
        layout="blur",
        src_w=1920,
        src_h=1080,
        fps=30,
        zoom="1",
        ass_file="s.ass",
        duration=60,
        crop=[0.0, 0.0, 0.75, 1.0],
        audio_input=1,
    )
    assert "crop=w='trunc(iw*0.7500/2)*2'" in g
    assert "[1:a]loudnorm" in g and "[0:a]" not in g
    plain = filter_graph(
        layout="blur", src_w=1920, src_h=1080, fps=30, zoom="1", ass_file="s.ass", duration=60
    )
    assert "[0:a]loudnorm" in plain and "crop=w='trunc(iw" not in plain


# --------------------------------------------------------------------------- mixage


def test_envelope_ducks_inside_intervals_with_ramps() -> None:
    sr = 1000
    g = mix.envelope(5000, sr, [(2.0, 3.0)], 12.0, ramp=0.2)
    assert g[500] == 1.0 and g[4500] == 1.0
    assert g[2500] == pytest.approx(10 ** (-12 / 20), rel=1e-4)
    assert 10 ** (-12 / 20) < g[1900] < 1.0  # rampe
    assert np.all(mix.envelope(100, sr, [], 12.0) == 1.0)


def test_narration_avoids_speech_moves_or_drops_lines() -> None:
    speech = [(0.0, 4.0), (6.0, 10.0)]
    placed, dropped = mix.place_narration(
        [(1.0, 1.5, "décalée"), (11.0, 2.0, "libre"), (5.0, 5.0, "trop longue")], speech, 14.0
    )
    texts = {p.text: p for p in placed}
    assert dropped == ["trop longue"]
    assert texts["libre"].t == 11.0 and not texts["libre"].moved
    moved = texts["décalée"]
    assert moved.moved and moved.t >= 4.0 and moved.t + 1.5 <= 6.0  # dans le trou 4–6 s
    # Pas de chevauchement entre lignes.
    spans = sorted((p.t, p.t + p.duration) for p in placed)
    assert all(a[1] <= b[0] for a, b in zip(spans, spans[1:], strict=False))


def test_loop_and_fit() -> None:
    music = np.ones((2, 300), dtype=np.float32)
    out = mix.loop_to(music, 1000, 100, fade=0.5)
    assert out.shape == (2, 1000) and out[0, 0] == 0 and out[0, 500] == 1.0 and out[0, -1] == 0
    assert mix.fit(np.ones((2, 10)), 4).shape == (2, 4)
    assert mix.fit(np.ones((2, 2)), 4)[0].tolist() == [1, 1, 0, 0]
    assert mix.merge_intervals([(0, 1), (1.2, 2), (5, 6)], gap=0.4) == [(0, 2), (5, 6)]


def test_wav_round_trip(tmp_path) -> None:  # type: ignore[no-untyped-def]
    a = (np.sin(np.linspace(0, 200, mix.SR)) * 0.5).astype(np.float32)
    stereo = np.stack([a, a * 2.0])  # > 1.0 : préservé en flottant
    mix.write_wav(tmp_path / "x.wav", stereo)
    back = mix.read_audio(tmp_path / "x.wav")
    assert back.shape == stereo.shape and np.allclose(back, stereo, atol=1e-5)


# --------------------------------------------------------------------------- plan


def _plan(**kw: object) -> ed.EditorialPlan:
    base = dict(
        hook_text="Ça part fort",
        hook_kind="original",
        hook_reason="",
        cta_text="",
        keywords=[],
        zooms=[],
        warnings=[],
    )
    return ed.EditorialPlan(**(base | kw))  # type: ignore[arg-type]


def test_narration_validation() -> None:
    ok = _plan(narration_needed=True, narration=[ed.NarrationLine(t=5, text="Il construit.")])
    assert ed.validate_plan(ok, [], 60, True).narration
    # Narration fournie alors que l'IA la juge inutile : ignorée.
    unneeded = _plan(narration_needed=False, narration=[ed.NarrationLine(t=5, text="x")])
    assert ed.validate_plan(unneeded, [], 60, True).narration == []
    with pytest.raises(ValueError, match="hors de l'extrait"):
        ed.validate_plan(
            _plan(narration_needed=True, narration=[ed.NarrationLine(t=70, text="x")]), [], 60, True
        )
    with pytest.raises(ValueError, match="lignes de narration"):
        lines = [ed.NarrationLine(t=i, text="x") for i in range(5)]
        ed.validate_plan(_plan(narration_needed=True, narration=lines), [], 60, True)
    assert ed.validate_plan(_plan(music_mood="disco"), [], 60, True).music_mood == ""
    # Anciens plans (Phase 4) toujours lisibles.
    legacy = _plan().model_dump()
    for k in ("narration_needed", "narration", "narration_reason", "music_mood"):
        legacy.pop(k)
    assert ed.EditorialPlan.model_validate(legacy).narration == []


def test_prompt_mentions_narration_rules_only_when_enabled() -> None:
    on = ed.editorial_system("fr", None, "P", None, narration=True, music=True)
    off = ed.editorial_system("fr", None, "P", None)
    assert "STRICTEMENT factuelles" in on and "SILENCE" in on and "énergique" in on
    assert "narration_needed = false" in off and "music_mood : chaîne vide" in off


# --------------------------------------------------------------------------- risques


def _report(audio=None, facecam=None, credits=None):  # type: ignore[no-untyped-def]
    return build_risk_report(
        source={"title": "T", "uploader": "U", "url": "u", "rights_status": "unknown"},
        profile={"name": "P"},
        plan={"hook_text": "h", "cta_text": "c", "zooms": [1]},
        plan_engine="llm",
        subtitles_translated=False,
        subtitles_enabled=True,
        candidate=None,
        qc=None,
        audio=audio,
        facecam=facecam,
        credits=credits,
    )


def test_risk_report_reflects_audio_facecam_and_credits() -> None:
    audio = {
        "source_music": {
            "status": "detected",
            "ratio": 0.6,
            "attenuated": True,
            "reduction_db": 15,
            "residual_ratio": 0.02,
        },
        "narration": {"status": "added", "lines": [{"t": 1, "text": "x"}]},
        "music": {"status": "added", "title": "Calme", "license": "CC BY 4.0"},
        "notes": ["note"],
    }
    credits = [{"kind": "music", "text": "Musique : « Calme » (CC BY 4.0)"}]
    facecam = {"status": "detected", "crop": [0, 0, 0.75, 1], "crop_side": "droite", "loss": 0.25}
    r = _report(audio, facecam, credits)
    assert r["audio_music"]["status"] == "atténuée" and "60%" in r["audio_music"]["detail"]
    assert r["facecam"]["status"] == "exclu" and "25%" in r["facecam"]["detail"]
    assert r["transformation"]["level"] == "élevée"
    assert "narration ou commentaire original" not in r["transformation"]["missing"]
    assert r["credits"] == credits and r["audio_notes"] == ["note"]
    assert any("crédit" in x for x in r["recommendations"])
    w = export_warnings(r, None)
    assert not any("Musique d'origine" in x for x in w)
    assert any("Crédits" in x for x in w)


def test_risk_report_warns_when_music_kept_or_facecam_uncertain() -> None:
    kept = {"source_music": {"status": "detected", "ratio": 0.5, "attenuated": False}}
    r = _report(kept, {"status": "uncertain", "warning": "Facecam incertain : test."})
    assert r["audio_music"]["status"] == "détectée"
    assert r["facecam"]["status"] == "incertain"
    w = export_warnings(r, None)
    assert "Musique d'origine conservée (risque de réclamation)." in w
    assert any(x.startswith("Facecam : Facecam incertain") for x in w)
    residual = {
        "source_music": {
            "status": "detected",
            "ratio": 0.8,
            "attenuated": True,
            "reduction_db": 15,
            "residual_ratio": 0.4,
        }
    }
    res = _report(residual)
    assert res["audio_music"]["status"] == "résiduelle"
    assert any("encore détectable" in x for x in export_warnings(res, None))
    assert _report({"source_music": {"status": "none", "ratio": 0}})["audio_music"]["status"] == (
        "absente"
    )
