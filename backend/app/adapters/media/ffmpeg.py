"""Adaptateur FFmpeg / ffprobe. Les commandes sont construites avec des listes d'arguments
fixes (jamais via un shell ni à partir de texte non validé)."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path

from app.adapters.types import CancelCheck, ProbeResult, ProgressCallback
from app.workers.errors import JobCancelled, StepError

logger = logging.getLogger("app.adapters.ffmpeg")

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _tool(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise StepError(f"{name} est introuvable dans le PATH. Installez FFmpeg (voir README).")
    return path


def _fps(rate: str | None) -> float | None:
    if not rate or rate in {"0/0", "0"}:
        return None
    num, _, den = rate.partition("/")
    try:
        value = float(num) / float(den or 1)
    except (ValueError, ZeroDivisionError):
        return None
    return round(value, 3) if value > 0 else None


class FfmpegTool:
    def probe(self, path: Path) -> ProbeResult:
        if not path.is_file():
            raise StepError(f"Fichier introuvable pour l'analyse : {path.name}")
        cmd = [
            _tool("ffprobe"),
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            creationflags=_NO_WINDOW,
            check=False,
        )
        if proc.returncode != 0:
            raise StepError(
                "ffprobe n'a pas pu lire le fichier (fichier corrompu ou tronqué ?).",
                technical=proc.stderr.strip()[:1000],
            )
        data = json.loads(proc.stdout or "{}")
        streams = data.get("streams", [])
        fmt = data.get("format", {})
        video = next(
            (
                s
                for s in streams
                if s.get("codec_type") == "video"
                and not s.get("disposition", {}).get("attached_pic")
            ),
            None,
        )
        audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
        try:
            duration = float(fmt.get("duration") or (video or audio or {}).get("duration") or 0)
        except ValueError:
            duration = 0.0
        return ProbeResult(
            duration_seconds=duration,
            format_name=fmt.get("format_name"),
            size_bytes=int(fmt["size"]) if fmt.get("size") else None,
            width=video.get("width") if video else None,
            height=video.get("height") if video else None,
            fps=_fps(video.get("avg_frame_rate") or video.get("r_frame_rate")) if video else None,
            video_codec=video.get("codec_name") if video else None,
            audio_codec=audio.get("codec_name") if audio else None,
            has_video=video is not None,
            has_audio=audio is not None,
            audio_sample_rate=int(audio["sample_rate"])
            if audio and audio.get("sample_rate")
            else None,
            audio_channels=audio.get("channels") if audio else None,
            raw={"format": fmt, "streams": streams},
        )

    def extract_audio(
        self,
        src: Path,
        dst: Path,
        duration_seconds: float,
        on_progress: ProgressCallback,
        check_cancel: CancelCheck,
    ) -> None:
        """Extrait l'audio en WAV PCM 16 bits, 16 kHz, mono (format attendu par l'ASR)."""
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_suffix(".tmp.wav")
        tmp.unlink(missing_ok=True)
        cmd = [
            _tool("ffmpeg"),
            "-hide_banner",
            "-nostdin",
            "-y",
            "-i",
            str(src),
            "-vn",
            "-sn",
            "-dn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            "-progress",
            "pipe:1",
            "-nostats",
            "-loglevel",
            "error",
            str(tmp),
        ]
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=_NO_WINDOW,
        )
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                check_cancel()
                key, _, value = line.strip().partition("=")
                if key == "out_time_us" and value.isdigit() and duration_seconds > 0:
                    seconds = int(value) / 1_000_000
                    on_progress(
                        min(seconds / duration_seconds, 0.99),
                        f"{seconds / 60:.1f} / {duration_seconds / 60:.1f} min",
                    )
            stderr = proc.stderr.read() if proc.stderr else ""
            code = proc.wait(timeout=60)
        except JobCancelled:
            proc.kill()
            proc.wait(timeout=10)
            tmp.unlink(missing_ok=True)
            raise
        if code != 0:
            tmp.unlink(missing_ok=True)
            raise StepError("FFmpeg n'a pas pu extraire l'audio.", technical=stderr.strip()[:1000])
        tmp.replace(dst)  # écriture atomique : pas de fichier partiel sous le nom final
        on_progress(1.0, f"{dst.stat().st_size / 1e6:.0f} Mo")
