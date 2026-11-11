"""Adaptateur FFmpeg / ffprobe. Les commandes sont construites avec des listes d'arguments
fixes (jamais via un shell ni à partir de texte non validé)."""

from __future__ import annotations

import contextlib
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

    # ------------------------------------------------------------------ Phase 3

    def _run(
        self,
        cmd: list[str],
        duration_seconds: float,
        on_progress: ProgressCallback,
        check_cancel: CancelCheck,
        failure: str,
        cleanup: list[Path],
        cwd: Path | None = None,
    ) -> None:
        """Lance FFmpeg avec suivi de progression (-progress pipe:1) et annulation sûre."""
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
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
            for path in cleanup:
                path.unlink(missing_ok=True)
            raise
        if code != 0:
            for path in cleanup:
                path.unlink(missing_ok=True)
            raise StepError(failure, technical=stderr.strip()[-1000:])

    def make_proxy(
        self,
        src: Path,
        dst: Path,
        height: int,
        duration_seconds: float,
        on_progress: ProgressCallback,
        check_cancel: CancelCheck,
        video_codec: str | None = None,
    ) -> None:
        """Copie d'analyse légère : H.264, hauteur réduite, 10 i/s, sans audio.

        Source AV1 : décodage matériel NVIDIA (av1_cuvid, ~5x plus rapide que libaom sur la
        machine cible), avec repli automatique sur le décodage logiciel en cas d'échec.
        """
        if video_codec == "av1" and shutil.which("nvidia-smi"):
            try:
                self._proxy(
                    src,
                    dst,
                    height,
                    duration_seconds,
                    on_progress,
                    check_cancel,
                    ["-c:v", "av1_cuvid"],
                )
                return
            except StepError as exc:
                logger.warning(
                    "Décodage AV1 matériel indisponible, repli logiciel : %s", exc.technical
                )
        self._proxy(src, dst, height, duration_seconds, on_progress, check_cancel, [])

    def _proxy(
        self,
        src: Path,
        dst: Path,
        height: int,
        duration_seconds: float,
        on_progress: ProgressCallback,
        check_cancel: CancelCheck,
        decoder: list[str],
    ) -> None:
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_suffix(".tmp.mp4")
        tmp.unlink(missing_ok=True)
        cmd = [
            _tool("ffmpeg"),
            "-hide_banner",
            "-nostdin",
            "-y",
            *decoder,
            "-i",
            str(src),
            "-an",
            "-sn",
            "-dn",
            "-vf",
            f"scale=-2:{height}:flags=bilinear,fps=10",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "26",
            "-pix_fmt",
            "yuv420p",
            "-g",
            "20",
            "-progress",
            "pipe:1",
            "-nostats",
            "-loglevel",
            "error",
            str(tmp),
        ]
        self._run(
            cmd,
            duration_seconds,
            on_progress,
            check_cancel,
            "FFmpeg n'a pas pu préparer la copie d'analyse de la vidéo.",
            [tmp],
        )
        tmp.replace(dst)

    def detect_scenes(
        self,
        video: Path,
        duration_seconds: float,
        threshold: float,
        on_progress: ProgressCallback,
        check_cancel: CancelCheck,
    ) -> list[tuple[float, float]]:
        """Changements de scène (filtre scdet) : liste de (instant en s, score 0..100)."""
        meta = video.with_name(video.stem + ".scenes.txt")
        meta.unlink(missing_ok=True)
        # Chemin du fichier passé au filtre : « / » et « : » échappé (syntaxe des filtres).
        meta_arg = meta.as_posix().replace(":", r"\:")
        cmd = [
            _tool("ffmpeg"),
            "-hide_banner",
            "-nostdin",
            "-y",
            "-i",
            str(video),
            "-vf",
            f"scdet=threshold={threshold}:sc_pass=1,metadata=print:file='{meta_arg}'",
            "-an",
            "-f",
            "null",
            "-progress",
            "pipe:1",
            "-nostats",
            "-loglevel",
            "error",
            "-",
        ]
        self._run(
            cmd,
            duration_seconds,
            on_progress,
            check_cancel,
            "FFmpeg n'a pas pu détecter les changements de scène.",
            [meta],
        )
        cuts: list[tuple[float, float]] = []
        current_time: float | None = None
        if meta.is_file():
            for line in meta.read_text(encoding="utf-8", errors="replace").splitlines():
                if "pts_time:" in line:
                    try:
                        current_time = float(line.rsplit("pts_time:", 1)[1].split()[0])
                    except ValueError:
                        current_time = None
                elif line.startswith("lavfi.scd.score=") and current_time is not None:
                    with contextlib.suppress(ValueError):
                        cuts.append((round(current_time, 3), float(line.split("=", 1)[1])))
            meta.unlink(missing_ok=True)
        on_progress(1.0, f"{len(cuts)} changements de scène")
        return cuts

    def extract_frame(self, video: Path, t: float, dst: Path, width: int) -> None:
        """Image JPEG à l'instant t (recherche rapide avant décodage)."""
        dst.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            _tool("ffmpeg"),
            "-hide_banner",
            "-nostdin",
            "-y",
            "-ss",
            f"{max(t, 0):.3f}",
            "-i",
            str(video),
            "-frames:v",
            "1",
            "-vf",
            f"scale={width}:-2",
            "-q:v",
            "4",
            "-loglevel",
            "error",
            str(dst),
        ]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            creationflags=_NO_WINDOW,
            check=False,
        )
        if proc.returncode != 0 or not dst.is_file():
            raise StepError(
                f"Impossible d'extraire l'image à {t:.1f} s.", technical=proc.stderr[-500:]
            )
