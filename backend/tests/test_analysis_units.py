"""Tests unitaires : signaux, fenêtres 61–180 s, scores, sélection, budget."""

from __future__ import annotations

import numpy as np
import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.analysis.candidates import (
    SelectionItem,
    generate_windows,
    overlap_ratio,
    select,
    weighted_score,
)
from app.analysis.signals import compute_signals
from app.core.config import Settings
from app.models import CRITERIA, ApiUsage
from app.services import budget


def _interest(duration: int, peaks: dict[int, float]) -> list[float]:
    curve = np.zeros(duration)
    for t, v in peaks.items():
        curve[max(0, t - 3) : t + 3] = v
    return curve.tolist()


def test_signals_detect_loud_bursts() -> None:
    sr = 16000
    audio = np.full(120 * sr, 0.01, dtype=np.float32)
    audio[50 * sr : 53 * sr] = 0.8  # rafale forte
    s = compute_signals(audio, words=[(10.0, 10.5), (11.0, 11.4)], scene_cuts=[30.0], duration=120)
    assert len(s.interest) == 120
    assert any(49 <= p <= 53 for p in s.audio_peaks)
    assert max(s.excitement[49:54]) == 1.0
    assert s.speech_rate[10] == 1 and s.speech_rate[11] == 1
    assert min(s.interest) >= 0 and max(s.interest) <= 1


@pytest.mark.parametrize("duration", [61.5, 200.0, 1800.0])
def test_windows_respect_duration_bounds(duration: float) -> None:
    d = int(duration)
    windows = generate_windows(
        duration=duration,
        interest=_interest(d, {d // 3: 1.0, 2 * d // 3: 0.8, 10: 0.5}),
        sentence_starts=[float(t) for t in range(0, d, 7)],
        sentence_ends=[float(t) + 5 for t in range(0, d, 7)],
        scene_cuts=[float(t) for t in range(3, d, 11)],
        min_duration=61,
        max_duration=180,
        max_candidates=10,
    )
    assert windows, "au moins un extrait attendu"
    for w in windows:
        assert 61 - 1e-6 <= w.duration <= 180 + 1e-6
        assert 0 <= w.start < w.end <= duration
    for i, a in enumerate(windows):
        for b in windows[i + 1 :]:
            assert overlap_ratio((a.start, a.end), (b.start, b.end)) <= 0.5


def test_too_short_video_gives_no_candidate() -> None:
    assert (
        generate_windows(
            duration=60.0,
            interest=[1.0] * 60,
            sentence_starts=[],
            sentence_ends=[],
            scene_cuts=[],
            min_duration=61,
            max_duration=180,
            max_candidates=5,
        )
        == []
    )


def test_profile_duration_bounds_are_used() -> None:
    windows = generate_windows(
        duration=600.0,
        interest=_interest(600, {300: 1.0}),
        sentence_starts=[],
        sentence_ends=[],
        scene_cuts=[],
        min_duration=90,
        max_duration=100,
        max_candidates=3,
    )
    assert windows and all(90 <= w.duration <= 100 for w in windows)


def test_weighted_score() -> None:
    scores = dict.fromkeys(CRITERIA, 5.0)
    assert weighted_score(scores, dict.fromkeys(CRITERIA, 1.0)) == 50.0
    scores["hook"] = 10.0
    weights = dict.fromkeys(CRITERIA, 0.0) | {"hook": 1.0}
    assert weighted_score(scores, weights) == 100.0


def test_selection_threshold_and_overlap() -> None:
    items = [
        SelectionItem("a", 0, 100, 80, True),
        SelectionItem("b", 10, 110, 75, True),  # chevauche a, moins bien noté
        SelectionItem("c", 300, 400, 55, True),  # sous le seuil
        SelectionItem("d", 500, 600, None, False),  # échec
        SelectionItem("e", 700, 800, 61, True),
    ]
    result = select(items, threshold=60)
    assert result["a"] == (True, None)
    assert result["b"][0] is False and "Chevauche" in result["b"][1]
    assert result["c"][0] is False and "Sous le seuil" in result["c"][1]
    assert result["d"] == (False, "Non évalué")
    assert result["e"] == (True, None)


def test_cost_and_budget(migrated: Settings, session_factory: sessionmaker[Session]) -> None:
    cost = budget.cost_usd(
        migrated, input_tokens=1_000_000, output_tokens=100_000, cache_read_tokens=1_000_000
    )
    assert cost == pytest.approx(2.0 + 1.0 + 0.10)
    with session_factory() as s:
        assert budget.monthly_cap(s, migrated) == 40.0
        budget.check_budget(s, migrated, 1.0)
        s.add(ApiUsage(provider="anthropic", model="m", purpose="t", cost_usd=39.5, status="ok"))
        s.commit()
        assert budget.month_spent(s) == pytest.approx(39.5)
        with pytest.raises(budget.BudgetExceeded):
            budget.check_budget(s, migrated, 1.0)
        budget.set_setting(s, budget.MONTHLY_CAP, 100.0)
        budget.check_budget(s, migrated, 1.0)
        budget.set_setting(s, budget.API_ENABLED, False)
        with pytest.raises(budget.BudgetExceeded, match="désactivée"):
            budget.check_budget(s, migrated, 0.0)


def test_api_key_is_never_exposed(client, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from pydantic import SecretStr

    client.app.state.settings.anthropic_api_key = SecretStr("sk-ant-secret-valeur")
    body = client.get("/api/settings/api").text
    assert "sk-ant" not in body
    assert '"key_configured":true' in body


def test_sentence_bounds_use_word_punctuation() -> None:
    import json as _json
    from types import SimpleNamespace

    from app.workers.pipeline.analyze import sentence_bounds

    def seg(start: float, end: float, words: list[tuple[float, float, str]]) -> SimpleNamespace:
        return SimpleNamespace(
            start_seconds=start,
            end_seconds=end,
            text=" ".join(w for _, _, w in words),
            words_json=_json.dumps([{"start": a, "end": b, "word": w} for a, b, w in words]),
        )

    # Le segment 2 commence au milieu d'une phrase : ce n'est pas un début de phrase.
    segments = [
        seg(0, 3, [(0, 1, " Bonjour"), (1, 2, " à"), (2, 3, " tous.")]),
        seg(3, 6, [(3, 4, " On"), (4, 5, " commence"), (5, 6, " la")]),
        seg(6, 9, [(6, 7, " mission"), (7, 8, " maintenant!"), (8, 9, " Allez")]),
    ]
    starts, ends = sentence_bounds(segments)  # type: ignore[arg-type]
    assert starts == [0.0, 3.0, 8.0]
    assert ends == [3.0, 8.0]


def test_transcript_is_split_at_exact_window_bounds(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """L'IA ne doit pas croire qu'un extrait commence au milieu d'une phrase à cause
    d'un segment Whisper qui chevauche la borne."""
    import json as _json
    from types import SimpleNamespace

    from app.analysis.judge import JudgeInput, user_content
    from app.workers.pipeline.analyze import _excerpt, transcript_for_window

    words = [(8, 9, " fin"), (9, 10, " précédente."), (10, 11, " Regarde"), (11, 12, " ça!")]
    seg = SimpleNamespace(
        start_seconds=8,
        end_seconds=12,
        text="fin précédente. Regarde ça!",
        words_json=_json.dumps([{"start": a, "end": b, "word": w} for a, b, w in words]),
    )
    lines = transcript_for_window([seg], start=10, end=80, context=10)  # type: ignore[list-item]
    assert lines == [(8.0, 10.0, "fin précédente."), (10.0, 12.0, "Regarde ça!")]
    text = user_content(JudgeInput(10, 80, lines, "", []))[0]["text"]
    assert "(hors extrait) fin précédente." in text
    assert "] Regarde ça!" in text and "(hors extrait) Regarde" not in text
    assert _excerpt([seg], 10, 80) == "Regarde ça!"  # type: ignore[list-item]
