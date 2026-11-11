"""Mixage audio du short (numpy) : jeu (musique d'origine éventuellement atténuée), narration,
musique de la bibliothèque. Le ducking s'appuie sur les horodatages CONNUS (mots de la
transcription, lignes de narration) plutôt que sur un compresseur : il est exact et testable.

Lecture et écriture passent par FFmpeg (flottants 32 bits, aucune dépendance audio de plus).
La normalisation finale (-14 LUFS) reste faite au rendu vidéo.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app.adapters.media.ffmpeg import _tool

SR = 44_100  # fréquence de travail (celle de Demucs)
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def db_to_gain(db: float) -> float:
    return float(10 ** (db / 20))


def read_audio(
    path: Path,
    *,
    sr: int = SR,
    channels: int = 2,
    start: float | None = None,
    duration: float | None = None,
) -> np.ndarray:
    """Audio décodé en flottants (channels, n). Fichier sans piste audio : silence."""
    cmd = [_tool("ffmpeg"), "-hide_banner", "-nostdin", "-loglevel", "error"]
    if start is not None:
        cmd += ["-ss", f"{max(start, 0):.3f}"]
    if duration is not None:
        cmd += ["-t", f"{duration:.3f}"]
    cmd += ["-i", str(path), "-vn", "-ac", str(channels), "-ar", str(sr), "-f", "f32le", "-"]
    proc = subprocess.run(
        cmd, capture_output=True, timeout=600, creationflags=_NO_WINDOW, check=False
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8", "replace").strip()[-400:])
    data = np.frombuffer(proc.stdout, dtype=np.float32)
    data = data[: len(data) - len(data) % channels]
    out = data.reshape(-1, channels).T.copy()
    if duration is not None and out.shape[1] == 0:
        out = np.zeros((channels, int(round(duration * sr))), dtype=np.float32)
    return out


def write_wav(path: Path, audio: np.ndarray, sr: int = SR) -> None:
    """WAV flottant 32 bits (préserve la marge avant la normalisation finale)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp.wav")
    raw = np.ascontiguousarray(audio.T.astype(np.float32)).tobytes()
    proc = subprocess.run(
        [
            _tool("ffmpeg"),
            "-hide_banner",
            "-nostdin",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "f32le",
            "-ar",
            str(sr),
            "-ac",
            str(audio.shape[0]),
            "-i",
            "-",
            "-c:a",
            "pcm_f32le",
            str(tmp),
        ],
        input=raw,
        capture_output=True,
        timeout=600,
        creationflags=_NO_WINDOW,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8", "replace").strip()[-400:])
    tmp.replace(path)


def encode_preview(src: Path, dst: Path) -> None:
    """Aperçu écoutable du mixage, au niveau final (-14 LUFS), en AAC."""
    tmp = dst.with_name(dst.stem + ".tmp" + dst.suffix)
    proc = subprocess.run(
        [
            _tool("ffmpeg"),
            "-hide_banner",
            "-nostdin",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(src),
            "-af",
            "loudnorm=I=-14:TP=-1.5:LRA=11",
            "-ar",
            "48000",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            str(tmp),
        ],
        capture_output=True,
        timeout=600,
        creationflags=_NO_WINDOW,
        check=False,
    )
    if proc.returncode != 0:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(proc.stderr.decode("utf-8", "replace").strip()[-400:])
    tmp.replace(dst)


def fit(audio: np.ndarray, n: int) -> np.ndarray:
    """Tronque ou complète par du silence à exactement n échantillons."""
    if audio.shape[1] >= n:
        return audio[:, :n]
    return np.pad(audio, ((0, 0), (0, n - audio.shape[1])))


def envelope(
    n: int, sr: int, intervals: list[tuple[float, float]], reduction_db: float, ramp: float = 0.15
) -> np.ndarray:
    """Gain par échantillon : 1 hors des intervalles, -reduction_db dedans, rampes linéaires."""
    gain = np.ones(n, dtype=np.float32)
    if not intervals or reduction_db <= 0:
        return gain
    low = db_to_gain(-reduction_db)
    t = np.arange(n, dtype=np.float32) / sr
    for a, b in intervals:
        # 1 → low sur [a - ramp, a], low sur [a, b], low → 1 sur [b, b + ramp]
        depth = np.clip(np.minimum((t - (a - ramp)) / ramp, ((b + ramp) - t) / ramp), 0, 1)
        gain = np.minimum(gain, 1 - depth * (1 - low))
    return gain


def merge_intervals(
    intervals: list[tuple[float, float]], gap: float = 0.4
) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for a, b in sorted(intervals):
        if out and a - out[-1][1] <= gap:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


@dataclass
class PlacedLine:
    t: float
    duration: float
    text: str
    moved: bool = False


def place_narration(
    lines: list[tuple[float, float, str]],
    speech: list[tuple[float, float]],
    total: float,
    tolerance: float = 0.3,
    margin: float = 0.15,
) -> tuple[list[PlacedLine], list[str]]:
    """Place chaque ligne (t souhaité, durée réelle, texte) sans couvrir la parole d'origine
    ni une autre ligne. Une ligne est décalée vers le trou le plus proche, ou abandonnée."""
    placed: list[PlacedLine] = []
    dropped: list[str] = []
    for t, dur, text in sorted(lines):
        busy = merge_intervals(speech + [(p.t, p.t + p.duration) for p in placed], gap=0)

        def overlap(
            start: float, busy: list[tuple[float, float]] = busy, dur: float = dur
        ) -> float:
            return sum(max(0.0, min(start + dur, b) - max(start, a)) for a, b in busy)

        start = min(max(t, 0.0), max(total - dur, 0.0))
        if dur <= total and overlap(start) <= tolerance:
            placed.append(PlacedLine(start, dur, text))
            continue
        # Trous de parole assez longs, le plus proche de l'instant souhaité.
        edges = [0.0] + [x for iv in busy for x in iv] + [total]
        gaps = [
            (edges[i] + margin, edges[i + 1] - margin)
            for i in range(0, len(edges) - 1, 2)
            if edges[i + 1] - edges[i] - 2 * margin >= dur
        ]
        if not gaps:
            dropped.append(text)
            continue
        best = min(
            (min(max(t, a), b - dur) for a, b in gaps),
            key=lambda s: abs(s - t),
        )
        placed.append(PlacedLine(best, dur, text, moved=True))
    placed.sort(key=lambda p: p.t)
    return placed, dropped


def loop_to(music: np.ndarray, n: int, sr: int, fade: float = 1.5) -> np.ndarray:
    """Musique bouclée ou coupée à n échantillons, avec fondu d'entrée et de sortie."""
    if music.shape[1] == 0:
        return np.zeros((2, n), dtype=np.float32)
    reps = int(np.ceil(n / music.shape[1]))
    out = np.tile(music, (1, reps))[:, :n].copy()
    k = min(int(fade * sr), n // 2)
    if k > 0:
        ramp = np.linspace(0, 1, k, dtype=np.float32)
        out[:, :k] *= ramp
        out[:, -k:] *= ramp[::-1]
    return out


def rms_db(audio: np.ndarray) -> float:
    v = float(np.sqrt(np.mean(np.square(audio)))) if audio.size else 0.0
    return 20 * np.log10(max(v, 1e-9))
