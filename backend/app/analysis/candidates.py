"""Proposition de fenêtres candidates (61–90 s) et sélection finale.

Règles du cahier des charges (§5, §7) appliquées ici :
- toute fenêtre dure STRICTEMENT entre min et max (61–90 s par défaut) ;
- une vidéo trop courte ne produit aucun candidat (pas d'extrait fabriqué) ;
- bornes calées autant que possible sur des débuts/fins de phrase ou des coupes ;
- doublons et chevauchements excessifs éliminés.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.models import CRITERIA


@dataclass
class Window:
    start: float
    end: float
    peak: float
    score: float  # intérêt local 0..1

    @property
    def duration(self) -> float:
        return self.end - self.start


def overlap_ratio(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Part de la plus courte des deux fenêtres recouverte par l'autre."""
    inter = max(0.0, min(a[1], b[1]) - max(a[0], b[0]))
    shortest = min(a[1] - a[0], b[1] - b[0])
    return inter / shortest if shortest > 0 else 0.0


def _local_peaks(curve: np.ndarray, min_gap: int, limit: int) -> list[int]:
    peaks: list[int] = []
    for i in np.argsort(-curve):
        if len(peaks) >= limit or curve[i] <= 0:
            break
        if all(abs(int(i) - p) >= min_gap for p in peaks):
            peaks.append(int(i))
    return peaks


def generate_windows(
    *,
    duration: float,
    interest: list[float],
    sentence_starts: list[float],
    sentence_ends: list[float],
    scene_cuts: list[float],
    min_duration: float,
    max_duration: float,
    max_candidates: int,
    max_overlap: float = 0.5,
) -> list[Window]:
    if duration < min_duration:
        return []
    curve = np.asarray(interest, dtype=float)
    if len(curve) == 0:
        return []
    s_starts, s_ends = sorted(set(sentence_starts)), sorted(set(sentence_ends))
    cuts = sorted(set(scene_cuts))
    lengths = sorted(
        {min(max(x, min_duration), max_duration) for x in (66.0, 75.0, 85.0, 105.0, 150.0)}
    )

    def pick_start(target: float, latest: float) -> tuple[float, bool]:
        # Priorité aux débuts de phrase ; les coupes de scène ne servent qu'à défaut
        # (passage sans parole), sinon l'extrait démarrerait au milieu d'une phrase.
        options = [x for x in s_starts if x <= latest and abs(x - target) <= 15.0]
        if options:
            return min(options, key=lambda x: abs(x - target)), True
        options = [x for x in cuts if x <= latest and abs(x - target) <= 8.0]
        if options:
            return min(options, key=lambda x: abs(x - target)), False
        return target, False

    def pick_end(start: float, target: float, earliest: float) -> tuple[float, bool]:
        lo, hi = start + min_duration, min(start + max_duration, duration)
        options = [x for x in s_ends if lo <= x <= hi and x >= earliest and abs(x - target) <= 25.0]
        if options:
            return min(options, key=lambda x: abs(x - target)), True
        options = [x for x in cuts if lo <= x <= hi and x >= earliest and abs(x - target) <= 8.0]
        if options:
            return min(options, key=lambda x: abs(x - target)), False
        return min(max(target, lo), hi), False

    proposals: list[Window] = []
    for peak in _local_peaks(curve, min_gap=20, limit=max_candidates * 4):
        for length in lengths:
            # Le moment fort arrive tôt (≈ 30 % de la durée) : accroche rapide.
            target_start = min(max(0.0, peak - 0.3 * length), max(0.0, duration - length))
            start, clean_start = pick_start(target_start, latest=max(peak - 2, 0.0))
            start = max(0.0, start)
            end, clean_end = pick_end(start, start + length, earliest=min(peak + 2, duration))
            if not min_duration - 1e-6 <= end - start <= max_duration + 1e-6:
                continue
            seg = curve[int(start) : max(int(end), int(start) + 1)]
            score = float(0.6 * seg.mean() + 0.4 * seg.max()) if len(seg) else 0.0
            # Léger bonus aux extraits qui commencent et finissent sur une phrase complète.
            score += 0.05 * clean_start + 0.05 * clean_end
            proposals.append(Window(round(start, 2), round(end, 2), float(peak), score))

    kept: list[Window] = []
    for w in sorted(proposals, key=lambda w: -w.score):
        if all(overlap_ratio((w.start, w.end), (k.start, k.end)) <= max_overlap for k in kept):
            kept.append(w)
        if len(kept) >= max_candidates:
            break
    return sorted(kept, key=lambda w: w.start)


def weighted_score(scores: dict[str, float], weights: dict[str, float]) -> float:
    """Note globale 0..100 = moyenne pondérée des critères (0..10)."""
    total_w = sum(weights.get(k, 0.0) for k in CRITERIA if k in scores)
    if total_w <= 0:
        return 0.0
    value = sum(scores[k] * weights.get(k, 0.0) for k in CRITERIA if k in scores) / total_w
    return round(value * 10, 1)


@dataclass
class SelectionItem:
    id: str
    start: float
    end: float
    overall: float | None
    eligible: bool  # noté (IA ou signaux), pas en échec
    confidence: float | None = None  # confiance de l'IA ; None = non applicable (signaux seuls)


def select(
    items: list[SelectionItem],
    threshold: float,
    max_overlap: float = 0.3,
    min_confidence: float = 0.0,
) -> dict[str, tuple[bool, str | None]]:
    """Retourne {id: (sélectionné, raison du rejet)}.

    En cas de chevauchement, le mieux noté est gardé.
    """
    result: dict[str, tuple[bool, str | None]] = {}
    kept: list[SelectionItem] = []
    for item in sorted(items, key=lambda i: -(i.overall or -1)):
        if not item.eligible or item.overall is None:
            result[item.id] = (False, "Non évalué")
        elif item.overall < threshold:
            result[item.id] = (False, f"Sous le seuil ({item.overall:.0f} < {threshold:.0f})")
        elif item.confidence is not None and item.confidence < min_confidence:
            result[item.id] = (
                False,
                f"Confiance de l'évaluation trop faible ({item.confidence:.2f} < "
                f"{min_confidence:.2f})",
            )
        elif any(
            overlap_ratio((item.start, item.end), (k.start, k.end)) > max_overlap for k in kept
        ):
            result[item.id] = (False, "Chevauche un extrait mieux noté")
        else:
            kept.append(item)
            result[item.id] = (True, None)
    return result
