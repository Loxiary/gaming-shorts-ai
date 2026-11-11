"""Rendu vertical 1080×1920 (H.264/AAC) et contrôle qualité du fichier produit.

Commandes construites en listes d'arguments fixes (aucun shell, aucun texte IA dans la
commande : l'accroche et les sous-titres passent par un fichier ASS échappé).
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from app.adapters.media.ffmpeg import FfmpegTool, _tool
from app.adapters.types import CancelCheck, ProgressCallback
from app.models import MAX_CLIP_SECONDS, MIN_CLIP_SECONDS
from app.render.editorial import ZoomMoment
from app.workers.errors import StepError

OUT_W, OUT_H = 1080, 1920
TARGET_LUFS = -14.0  # niveau courant des plateformes de shorts
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def zoom_expression(zooms: list[ZoomMoment], intensity: float) -> str:
    """Facteur d'agrandissement en fonction de t : bosse sinusoïdale par zoom."""
    if intensity <= 0 or not zooms:
        return "1"
    terms = [
        f"between(t,{z.t:.3f},{z.t + z.duration:.3f})*sin(PI*(t-{z.t:.3f})/{z.duration:.3f})"
        for z in zooms
    ]
    return f"1+{intensity:.3f}*({'+'.join(terms)})"


def filter_graph(
    *,
    layout: str,
    src_w: int,
    src_h: int,
    fps: float,
    zoom: str,
    ass_file: str,
    duration: float,
) -> str:
    fonts = ":fontsdir='C\\:/Windows/Fonts'" if sys.platform == "win32" else ""
    fade_out = max(duration - 0.3, 0)
    z = f"({zoom})"
    if layout == "fill":
        video = (
            f"[0:v]fps={fps:g},scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=increase,"
            f"scale=w='trunc(iw*{z}/2)*2':h=-2:eval=frame,crop={OUT_W}:{OUT_H}"
        )
    else:
        fg_h = int(round(OUT_W * src_h / src_w / 2) * 2)
        fg_h = min(fg_h, OUT_H)
        video = (
            f"[0:v]fps={fps:g},split=2[bg][fg];"
            f"[bg]scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=increase,crop={OUT_W}:{OUT_H},"
            f"gblur=sigma=28,eq=brightness=-0.08[bgb];"
            f"[fg]scale=w='trunc({OUT_W}*{z}/2)*2':h=-2:eval=frame,crop={OUT_W}:{fg_h}[fgz];"
            f"[bgb][fgz]overlay=x=(W-w)/2:y=(H-h)/2"
        )
    return (
        f"{video},ass={ass_file}{fonts},format=yuv420p[v];"
        f"[0:a]loudnorm=I={TARGET_LUFS}:TP=-1.5:LRA=11,afade=t=in:d=0.3,"
        f"afade=t=out:st={fade_out:.3f}:d=0.3,aresample=48000[a]"
    )


def render_short(
    *,
    source: Path,
    workdir: Path,
    ass_name: str,
    out_name: str,
    start: float,
    duration: float,
    layout: str,
    encoder: str,
    src_codec: str | None,
    src_w: int,
    src_h: int,
    src_fps: float | None,
    zooms: list[ZoomMoment],
    zoom_intensity: float,
    on_progress: ProgressCallback,
    check_cancel: CancelCheck,
    x264_preset: str = "faster",
) -> Path:
    fps = min(src_fps or 30.0, 60.0)
    graph = filter_graph(
        layout=layout,
        src_w=src_w,
        src_h=src_h,
        fps=fps,
        zoom=zoom_expression(zooms, zoom_intensity),
        ass_file=ass_name,
        duration=duration,
    )
    codec_args = (
        ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "21", "-b:v", "0"]
        if encoder == "h264_nvenc"
        else ["-c:v", "libx264", "-preset", x264_preset, "-crf", "20"]
    )
    tmp = workdir / f"{out_name}.tmp.mp4"
    final = workdir / f"{out_name}.mp4"

    def command(decoder: list[str]) -> list[str]:
        return [
            _tool("ffmpeg"),
            "-hide_banner",
            "-nostdin",
            "-y",
            *decoder,
            "-ss",
            f"{start:.3f}",
            "-t",
            f"{duration:.3f}",
            "-i",
            str(source),
            "-filter_complex",
            graph,
            "-map",
            "[v]",
            "-map",
            "[a]",
            *codec_args,
            "-profile:v",
            "high",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            "-progress",
            "pipe:1",
            "-nostats",
            "-loglevel",
            "error",
            tmp.name,
        ]

    tool = FfmpegTool()
    decoders: list[list[str]] = [[]]
    if src_codec == "av1" and shutil.which("nvidia-smi"):
        decoders.insert(0, ["-c:v", "av1_cuvid"])  # ~5x plus rapide que libaom (cf. Phase 3)
    last_error: StepError | None = None
    for decoder in decoders:
        try:
            _run_in(tool, command(decoder), workdir, duration, on_progress, check_cancel, tmp)
            tmp.replace(final)
            return final
        except StepError as exc:
            last_error = exc
    assert last_error is not None
    raise last_error


def _run_in(
    tool: FfmpegTool,
    cmd: list[str],
    cwd: Path,
    duration: float,
    on_progress: ProgressCallback,
    check_cancel: CancelCheck,
    tmp: Path,
) -> None:
    """FFmpeg lancé depuis le dossier de travail : le chemin du fichier ASS reste relatif
    (évite l'échappement des « C: » dans la syntaxe des filtres)."""
    tool._run(
        cmd,
        duration,
        on_progress,
        check_cancel,
        "FFmpeg n'a pas pu produire le short.",
        [tmp],
        cwd=cwd,
    )


# --------------------------------------------------------------------------- QC


def measure_loudness(path: Path) -> dict[str, float | None]:
    proc = subprocess.run(
        [
            _tool("ffmpeg"),
            "-hide_banner",
            "-nostdin",
            "-nostats",
            "-i",
            str(path),
            "-vn",
            "-af",
            "ebur128=peak=true",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
        creationflags=_NO_WINDOW,
        check=False,
    )
    summary = proc.stderr.rsplit("Summary:", 1)[-1]

    def grab(pattern: str) -> float | None:
        m = re.search(pattern, summary)
        return float(m.group(1)) if m else None

    return {
        "integrated_lufs": grab(r"I:\s+(-?[\d.]+) LUFS"),
        "true_peak_dbfs": grab(r"Peak:\s+(-?[\d.]+) dBFS"),
        "loudness_range_lu": grab(r"LRA:\s+(-?[\d.]+) LU"),
    }


def decode_errors(path: Path) -> str:
    proc = subprocess.run(
        [
            _tool("ffmpeg"),
            "-hide_banner",
            "-nostdin",
            "-v",
            "error",
            "-i",
            str(path),
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
        creationflags=_NO_WINDOW,
        check=False,
    )
    return (proc.stderr or "").strip() if proc.returncode == 0 else (proc.stderr or "échec").strip()


def quality_check(path: Path, expected_duration: float) -> dict[str, Any]:
    """Contrôles du FICHIER PRODUIT. ``critical`` : bloque l'export ; ``warning`` : informe."""
    checks: list[dict[str, Any]] = []

    def add(key: str, label: str, ok: bool, detail: str, level: str = "critical") -> None:
        checks.append(
            {
                "key": key,
                "label": label,
                "ok": ok,
                "detail": detail,
                "level": level if not ok else "ok",
            }
        )

    exists = path.is_file() and path.stat().st_size > 0
    add(
        "file",
        "Fichier présent et non vide",
        exists,
        f"{path.stat().st_size / 1e6:.1f} Mo" if exists else "absent ou vide",
    )
    if not exists:
        return {"passed": False, "checks": checks, "measures": {}}

    probe = FfmpegTool().probe(path)
    raw_streams = probe.raw.get("streams", [])
    video = next((s for s in raw_streams if s.get("codec_type") == "video"), {})  # type: ignore[union-attr]
    audio = next((s for s in raw_streams if s.get("codec_type") == "audio"), {})  # type: ignore[union-attr]
    d = probe.duration_seconds
    add(
        "duration",
        f"Durée entre {MIN_CLIP_SECONDS:.0f} et {MAX_CLIP_SECONDS:.0f} s",
        MIN_CLIP_SECONDS - 0.05 <= d <= MAX_CLIP_SECONDS + 0.05,
        f"{d:.2f} s",
    )
    add(
        "duration_match",
        "Durée conforme à l'extrait",
        abs(d - expected_duration) <= 0.25,
        f"{d:.2f} s pour {expected_duration:.2f} s attendues",
        level="warning",
    )
    add(
        "resolution",
        "Résolution 1080×1920 (9:16)",
        (probe.width, probe.height) == (OUT_W, OUT_H),
        f"{probe.width}×{probe.height}",
    )
    add("video_codec", "Vidéo H.264", probe.video_codec == "h264", str(probe.video_codec))
    add(
        "pix_fmt",
        "Format de pixels compatible (yuv420p)",
        video.get("pix_fmt") == "yuv420p",
        str(video.get("pix_fmt")),
    )  # type: ignore[union-attr]
    add("audio", "Piste audio AAC présente", probe.audio_codec == "aac", str(probe.audio_codec))
    errors = decode_errors(path)
    add(
        "decode",
        "Lecture complète sans erreur (fichier non tronqué)",
        not errors,
        "aucune erreur" if not errors else errors[:300],
    )
    v_dur = float(video.get("duration") or d)  # type: ignore[union-attr]
    a_dur = float(audio.get("duration") or d)  # type: ignore[union-attr]
    add(
        "av_sync",
        "Durées audio et vidéo alignées (synchronisation)",
        abs(v_dur - a_dur) <= 0.1,
        f"écart {abs(v_dur - a_dur) * 1000:.0f} ms",
        level="warning",
    )
    fps = probe.fps or 0
    add("fps", "Cadence d'au moins 24 i/s", fps >= 24, f"{fps:g} i/s", level="warning")
    loud = measure_loudness(path)
    lufs, peak = loud["integrated_lufs"], loud["true_peak_dbfs"]
    add(
        "loudness",
        "Volume proche de -14 LUFS (±2)",
        lufs is not None and abs(lufs - TARGET_LUFS) <= 2,
        f"{lufs} LUFS" if lufs is not None else "mesure impossible",
        level="warning",
    )
    add(
        "clipping",
        "Pas de saturation (crête < -1 dBFS)",
        peak is not None and peak < -1.0,
        f"crête {peak} dBFS" if peak is not None else "mesure impossible",
        level="warning",
    )
    passed = all(c["ok"] or c["level"] == "warning" for c in checks)
    return {
        "passed": passed,
        "checks": checks,
        "measures": {
            "duration": round(d, 3),
            "fps": fps,
            "size_bytes": path.stat().st_size,
            **loud,
        },
    }
