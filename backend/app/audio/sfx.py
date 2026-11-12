"""Bruitages synthétisés par le code (Phase 7) : aucun fichier tiers, donc aucune licence.

- « whoosh » : souffle filtré dont la fréquence balaie vers le haut (transitions, flash) ;
- « impact » : coup sourd grave à hauteur descendante + attaque bruitée (tremblement).

Les sons sont déterministes (graine fixe) : un même montage donne le même mixage.
"""

from __future__ import annotations

import numpy as np

SR = 44_100


def _normalize(x: np.ndarray, peak: float = 0.9) -> np.ndarray:
    m = float(np.max(np.abs(x))) if x.size else 0.0
    return (x / m * peak).astype(np.float32) if m > 0 else x.astype(np.float32)


def whoosh(duration: float = 0.6, sr: int = SR, seed: int = 7) -> np.ndarray:
    """Souffle stéréo (2, n) : bruit blanc filtré par une bande qui monte de 300 Hz à 4 kHz,
    enveloppe en cloche, légère ouverture stéréo."""
    n = max(int(duration * sr), 256)
    rng = np.random.default_rng(seed)
    noise = rng.standard_normal((2, n))
    out = np.zeros((2, n))
    block, hop = 2048, 512
    window = np.hanning(block)
    freqs = np.fft.rfftfreq(block, 1 / sr)
    for start in range(0, n, hop):
        seg = np.zeros((2, block))
        chunk = noise[:, start : start + block]
        seg[:, : chunk.shape[1]] = chunk
        progress = min(start / n, 1.0)
        center = 300 * (4000 / 300) ** progress
        mask = np.exp(-0.5 * (np.log(np.maximum(freqs, 1) / center) / 0.45) ** 2)
        filtered = np.fft.irfft(np.fft.rfft(seg * window, axis=1) * mask, n=block, axis=1)
        end = min(start + block, n)
        out[:, start:end] += filtered[:, : end - start]
    t = np.linspace(0, 1, n)
    env = np.sin(np.pi * t) ** 1.5
    out *= env
    out[1] = np.roll(out[1], int(0.004 * sr))  # léger décalage : impression d'espace
    return _normalize(out, 0.8)


def impact(duration: float = 0.5, sr: int = SR, seed: int = 11) -> np.ndarray:
    """Coup sourd stéréo (2, n) : sinus 90 → 40 Hz à décroissance rapide + attaque bruitée."""
    n = max(int(duration * sr), 256)
    t = np.arange(n) / sr
    freq = 40 + 50 * np.exp(-t * 12)
    phase = 2 * np.pi * np.cumsum(freq) / sr
    body = np.sin(phase) * np.exp(-t * 7)
    rng = np.random.default_rng(seed)
    click = rng.standard_normal(n) * np.exp(-t * 60) * 0.5
    mono = body + click
    return _normalize(np.stack([mono, mono]), 0.9)


def build_track(
    events: list[tuple[float, str]], n: int, sr: int = SR
) -> tuple[np.ndarray, list[dict[str, float | str]]]:
    """Piste (2, n) avec chaque bruitage à son instant. ``events`` : (t, « whoosh » | « impact »).
    Un souffle est centré pour culminer à t ; un impact démarre à t."""
    track = np.zeros((2, n), dtype=np.float32)
    placed: list[dict[str, float | str]] = []
    sounds = {"whoosh": whoosh(), "impact": impact()}
    for t, kind in sorted(events):
        snd = sounds[kind]
        start = int(t * sr) - (snd.shape[1] // 2 if kind == "whoosh" else 0)
        a, b = max(start, 0), min(start + snd.shape[1], n)
        if b <= a:
            continue
        track[:, a:b] += snd[:, a - start : b - start]
        placed.append({"t": round(t, 2), "kind": kind})
    return track, placed
