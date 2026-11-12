"""Adaptateur yt-dlp pour YouTube.

Règles : uniquement des vidéos publiques ou non répertoriées accessibles sans compte.
Aucun cookie de navigateur, aucune authentification, aucun contournement de DRM, de
restriction d'âge, de géoblocage ou de protection anti-robot. En cas de refus de la
plateforme, l'étape échoue avec un message explicite.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

import yt_dlp
from yt_dlp.utils import DownloadError

from app.adapters.types import CancelCheck, ProgressCallback, SourceMetadata
from app.core.config import Settings
from app.workers.errors import JobCancelled, StepError

logger = logging.getLogger("app.adapters.youtube")

_REJECTED_LIVE = {"is_live", "is_upcoming", "post_live"}
_REJECTED_AVAILABILITY = {"needs_auth", "premium_only", "subscriber_only"}
_METADATA_KEYS = (
    "id",
    "title",
    "uploader",
    "uploader_id",
    "channel",
    "channel_id",
    "channel_url",
    "upload_date",
    "duration",
    "license",
    "categories",
    "tags",
    "availability",
    "live_status",
    "webpage_url",
    "language",
    "age_limit",
    "was_live",
)

# Messages yt-dlp connus -> message utilisateur (aucune tentative de contournement).
_ERROR_HINTS = (
    ("private video", "Vidéo privée : elle n'est pas accessible."),
    (
        "confirm your age",
        "Vidéo soumise à une restriction d'âge (connexion requise) : non prise en charge.",
    ),
    (
        "not a bot",
        "YouTube a refusé la requête (vérification anti-robot). Réessayez plus tard ; "
        "l'application ne contourne pas cette protection.",
    ),
    ("drm", "Vidéo protégée par DRM : non prise en charge."),
    ("members-only", "Vidéo réservée aux membres : non prise en charge."),
    (
        "not available in your country",
        "Vidéo non disponible dans votre pays : non prise en charge.",
    ),
    ("video unavailable", "Vidéo indisponible (supprimée ou inaccessible)."),
    (
        "unable to download webpage",
        "Connexion à YouTube impossible : vérifiez votre accès Internet.",
    ),
    ("timed out", "Délai de connexion dépassé : vérifiez votre accès Internet puis relancez."),
    ("no space left", "Espace disque insuffisant."),
)


def _friendly(exc: Exception) -> StepError:
    text = str(exc)
    lowered = text.lower()
    for needle, message in _ERROR_HINTS:
        if needle in lowered:
            return StepError(message, technical=text)
    return StepError(f"Échec yt-dlp : {text.removeprefix('ERROR: ')[:300]}", technical=text)


class _YtdlpLogger:
    def debug(self, msg: str) -> None:
        if not msg.startswith("[debug] "):
            logger.debug(msg)

    def info(self, msg: str) -> None:
        logger.debug(msg)

    def warning(self, msg: str) -> None:
        logger.warning(msg)

    def error(self, msg: str) -> None:
        logger.error(msg)


class YouTubeDownloader:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _format(self) -> str:
        # H.264 (avc1) en priorité : décodage rapide partout (FFmpeg « essentials » n'a pas
        # libdav1d, l'AV1 n'y est décodé que par libaom, lent, ou NVDEC). Repli : autres codecs.
        h = self.settings.max_download_height
        return (
            f"bv*[height<={h}][vcodec^=avc1]+ba[ext=m4a]/"
            f"bv*[height<={h}][ext=mp4]+ba[ext=m4a]/"
            f"bv*[height<={h}]+ba/b[height<={h}]"
        )

    def _base_options(self) -> dict[str, Any]:
        opts: dict[str, Any] = {
            "quiet": True,
            "no_warnings": False,
            "noprogress": True,
            "noplaylist": True,
            "logger": _YtdlpLogger(),
            "format": self._format(),
            "js_runtimes": {self.settings.ytdlp_js_runtime: {}},
            "socket_timeout": 30,
            "retries": 5,
            "fragment_retries": 5,
            # Jamais de cookies ni d'identifiants : accès public uniquement.
            "cookiefile": None,
        }
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg:
            opts["ffmpeg_location"] = str(Path(ffmpeg).parent)
        return opts

    # ------------------------------------------------------------------ métadonnées

    def fetch_metadata(self, url: str) -> SourceMetadata:
        try:
            with yt_dlp.YoutubeDL(self._base_options()) as ydl:
                info = ydl.extract_info(url, download=False)
        except DownloadError as exc:
            raise _friendly(exc) from exc
        if not isinstance(info, dict):
            raise StepError("Réponse inattendue de yt-dlp (aucune métadonnée).")
        if info.get("_type") == "playlist":
            raise StepError("Ce lien désigne une playlist : importez chaque vidéo séparément.")
        if info.get("live_status") in _REJECTED_LIVE:
            raise StepError("Diffusion en direct (ou à venir) : attendez la fin du direct.")
        if info.get("availability") in _REJECTED_AVAILABILITY:
            raise StepError(
                "Vidéo accessible uniquement avec un compte (abonnés, membres, premium) : "
                "non prise en charge."
            )
        formats = info.get("requested_formats") or [info]
        if any(f.get("has_drm") for f in formats):
            raise StepError("Vidéo protégée par DRM : non prise en charge.")
        duration = info.get("duration")
        if duration and duration > self.settings.max_source_minutes * 60:
            raise StepError(
                f"Vidéo trop longue ({duration / 60:.0f} min) : la limite configurée est "
                f"{self.settings.max_source_minutes} min (GSA_MAX_SOURCE_MINUTES)."
            )
        size = 0
        for f in formats:
            size += int(f.get("filesize") or f.get("filesize_approx") or 0)
        return SourceMetadata(
            external_id=str(info.get("id")),
            title=info.get("title"),
            uploader=info.get("uploader") or info.get("channel"),
            channel_id=info.get("channel_id"),
            channel_url=info.get("channel_url") or info.get("uploader_url"),
            upload_date=info.get("upload_date"),
            duration_seconds=float(duration) if duration else None,
            platform_license=info.get("license"),
            webpage_url=info.get("webpage_url"),
            estimated_size_bytes=size or None,
            raw={k: info.get(k) for k in _METADATA_KEYS if info.get(k) is not None},
        )

    # ------------------------------------------------------------------ téléchargement

    def download(
        self, url: str, dest_dir: Path, on_progress: ProgressCallback, check_cancel: CancelCheck
    ) -> Path:
        dest_dir.mkdir(parents=True, exist_ok=True)
        files: dict[str, tuple[int, int]] = {}
        cancelled: list[JobCancelled] = []

        def hook(d: dict[str, Any]) -> None:
            try:
                check_cancel()
            except JobCancelled as exc:
                cancelled.append(exc)
                raise
            name = str(d.get("filename") or d.get("tmpfilename") or "?")
            done = int(d.get("downloaded_bytes") or 0)
            total = int(d.get("total_bytes") or d.get("total_bytes_estimate") or 0)
            if d.get("status") == "finished":
                total = total or done
                done = total
            files[name] = (done, total)
            sum_done = sum(v[0] for v in files.values())
            sum_total = sum(v[1] for v in files.values())
            fraction = sum_done / sum_total if sum_total else 0.0
            on_progress(
                min(fraction, 0.99),
                f"{sum_done / 1e6:.0f} Mo / {sum_total / 1e6:.0f} Mo" if sum_total else None,
            )

        opts = self._base_options() | {
            "outtmpl": str(dest_dir / "source.%(ext)s"),
            "merge_output_format": "mp4",
            "continuedl": True,
            "progress_hooks": [hook],
            "paths": {"temp": str(dest_dir)},
        }
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
        except JobCancelled:
            raise
        except DownloadError as exc:
            if cancelled:
                raise cancelled[0] from exc
            raise _friendly(exc) from exc
        if cancelled:
            raise cancelled[0]

        downloads = (info or {}).get("requested_downloads") or []
        path = Path(downloads[0]["filepath"]) if downloads else None
        if path is None or not path.is_file():
            candidates = sorted(dest_dir.glob("source.*"), key=lambda p: p.stat().st_size)
            path = next((p for p in reversed(candidates) if p.suffix != ".part"), None)
        if path is None or not path.is_file():
            raise StepError("Téléchargement terminé mais fichier vidéo introuvable.")
        on_progress(1.0, f"{path.stat().st_size / 1e6:.0f} Mo")
        return path
