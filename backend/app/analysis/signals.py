"""Signaux locaux seconde par seconde (aucune IA, aucun coût).

- Énergie audio : niveau RMS en dB et « excitation » = écart au niveau habituel de la vidéo
  (médiane / écart absolu médian). Un pic signale un son nettement plus fort que d'habitude
  (cri, explosion, musique qui monte) — ce n'est PAS une reconnaissance de rires ou de cris.
- Parole : nombre de mots prononcés par seconde (transcription horodatée).
- Montage : densité des changements de scène détectés.
- Intérêt : combinaison lissée des trois, normalisée 0..1, utilisée pour proposer des fenêtres.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

SAMPLE_RATE = 16_000


@dataclass
class Signals:
    duration: float
    loudness_db: list[float]  # par seconde
    excitement: list[float]  # 0..1
    speech_rate: list[float]  # mots / s
    scene_density: list[float]  # changements / s (lissé)
    interest: list[float]  # 0..1
    audio_peaks: list[float] = field(default_factory=list)  # instants (s)

    def to_json(self) -> dict[str, object]:
        r = lambda xs: [round(x, 4) for x in xs]  # noqa: E731
        return {
            "duration": round(self.duration, 3),
            "loudness_db": r(self.loudness_db),
            "excitement": r(self.excitement),
            "speech_rate": r(self.speech_rate),
            "scene_density": r(self.scene_density),
            "interest": r(self.interest),
            "audio_peaks": r(self.audio_peaks),
        }

    @classmethod
    def from_json(cls, data: dict) -> Signals:  # type: ignore[type-arg]
        return cls(
            duration=float(data["duration"]),
            loudness_db=list(data["loudness_db"]),
            excitement=list(data["excitement"]),
            speech_rate=list(data["speech_rate"]),
            scene_density=list(data["scene_density"]),
            interest=list(data["interest"]),
            audio_peaks=list(data.get("audio_peaks", [])),
        )


def _smooth(x: np.ndarray, width: int) -> np.ndarray:
    if width <= 1 or len(x) == 0:
        return x
    kernel = np.ones(width) / width
    return np.convolve(x, kernel, mode="same")


def _norm01(x: np.ndarray) -> np.ndarray:
    if len(x) == 0:
        return x
    lo, hi = float(np.percentile(x, 5)), float(np.percentile(x, 98))
    if hi - lo < 1e-9:
        return np.zeros_like(x)
    return np.clip((x - lo) / (hi - lo), 0.0, 1.0)


def loudness_per_second(audio: np.ndarray, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    """Niveau RMS (dBFS) par seconde."""
    n = len(audio) // sample_rate
    if n == 0:
        return np.zeros(0)
    frames = audio[: n * sample_rate].reshape(n, sample_rate).astype(np.float64)
    rms = np.sqrt(np.mean(frames**2, axis=1))
    return 20 * np.log10(np.maximum(rms, 1e-6))


def compute_signals(
    audio: np.ndarray,
    words: list[tuple[float, float]],
    scene_cuts: list[float],
    duration: float,
) -> Signals:
    """``words`` : (début, fin) de chaque mot ; ``scene_cuts`` : instants des changements."""
    n = max(int(np.ceil(duration)), 1)
    loud = loudness_per_second(audio)
    loud = np.pad(
        loud, (0, max(0, n - len(loud))), constant_values=loud.min() if len(loud) else -60
    )[:n]

    median = float(np.median(loud))
    mad = float(np.median(np.abs(loud - median))) or 1.0
    z = (loud - median) / (1.4826 * mad)
    excitement = np.clip(z / 3.0, 0.0, 1.0)  # 3 écarts au-dessus du niveau habituel = 1

    speech = np.zeros(n)
    for start, end in words:
        i = min(int((start + end) / 2), n - 1)
        if i >= 0:
            speech[i] += 1

    cuts = np.zeros(n)
    for t in scene_cuts:
        i = min(int(t), n - 1)
        if i >= 0:
            cuts[i] += 1
    scene_density = _smooth(cuts, 5)

    interest = (
        0.45 * _norm01(_smooth(excitement, 3))
        + 0.35 * _norm01(_smooth(speech, 5))
        + 0.20 * _norm01(scene_density)
    )
    interest = _smooth(interest, 5)
    interest = _norm01(interest) if len(interest) else interest

    # Pics audio : maxima locaux nets, espacés d'au moins 5 s.
    peaks: list[float] = []
    order = np.argsort(-z)
    for i in order:
        if z[i] < 2.0 or len(peaks) >= 50:
            break
        if all(abs(i - p) >= 5 for p in peaks):
            peaks.append(float(i))
    return Signals(
        duration=duration,
        loudness_db=loud.tolist(),
        excitement=excitement.tolist(),
        speech_rate=speech.tolist(),
        scene_density=scene_density.tolist(),
        interest=interest.tolist(),
        audio_peaks=sorted(peaks),
    )
