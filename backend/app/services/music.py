"""Bibliothèque musicale locale : les morceaux déposés dans GSA_DATA_DIR/music.

L'application ne télécharge aucune musique. L'utilisateur dépose ses fichiers, renseigne la
licence et confirme disposer de l'autorisation ; seuls ces morceaux sont utilisables.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.media.ffmpeg import FfmpegTool
from app.core.config import Settings
from app.core.errors import AppError, NotFoundError
from app.models import MusicTrack
from app.models_registry import ALL_ASSETS, PIPER_VOICES
from app.schemas.music import AudioAssetOut, MusicTrackIn, MusicTrackOut

logger = logging.getLogger(__name__)
AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".opus", ".aac"}


def to_out(t: MusicTrack) -> MusicTrackOut:
    return MusicTrackOut(
        id=t.id,
        file_path=t.file_path,
        file_name=Path(t.file_path).name,
        file_size_bytes=t.file_size_bytes,
        duration_seconds=t.duration_seconds,
        title=t.title,
        artist=t.artist,
        license=t.license,
        source_url=t.source_url,
        moods=t.mood_list,
        notes=t.notes,
        license_confirmed=t.license_confirmed,
        usable=t.usable,
        audio_url=f"/api/music/{t.id}/audio",
    )


def list_tracks(session: Session) -> list[MusicTrack]:
    return list(session.scalars(select(MusicTrack).order_by(MusicTrack.file_path)))


def get_track(session: Session, track_id: str) -> MusicTrack:
    t = session.get(MusicTrack, track_id)
    if t is None:
        raise NotFoundError(f"Morceau introuvable : {track_id}")
    return t


def scan_library(session: Session, settings: Settings) -> dict[str, Any]:
    """Ajoute les nouveaux fichiers du dossier musique, retire les fiches de fichiers disparus.
    Les licences déjà saisies sont conservées."""
    root = settings.subdir("music")
    known = {t.file_path: t for t in list_tracks(session)}
    found: set[str] = set()
    added = 0
    errors: list[str] = []
    media = FfmpegTool()
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in AUDIO_EXTENSIONS:
            continue
        rel = settings.to_relative(path)
        found.add(rel)
        if rel in known:
            continue
        try:
            info = media.probe(path)
        except Exception as exc:  # noqa: BLE001 - fichier illisible : signalé, pas bloquant
            errors.append(f"{path.name} : illisible ({exc})")
            continue
        if not info.has_audio:
            errors.append(f"{path.name} : aucune piste audio")
            continue
        session.add(
            MusicTrack(
                file_path=rel,
                file_size_bytes=path.stat().st_size,
                duration_seconds=round(info.duration_seconds, 2),
                title=path.stem.replace("_", " "),
            )
        )
        added += 1
    removed = 0
    for rel, t in known.items():
        if rel not in found:
            session.delete(t)
            removed += 1
    session.commit()
    logger.info("Bibliothèque musicale : %d ajouté(s), %d retiré(s)", added, removed)
    return {
        "added": added,
        "removed": removed,
        "total": len(found) - len(errors),
        "errors": errors,
        "folder": str(root),
    }


def update_track(session: Session, track_id: str, data: MusicTrackIn) -> MusicTrack:
    t = get_track(session, track_id)
    if data.license_confirmed and not (data.license and data.license.strip()):
        raise AppError("Renseignez la licence avant de confirmer l'autorisation.")
    t.title = data.title
    t.artist = data.artist
    t.license = data.license
    t.source_url = data.source_url
    t.moods = ", ".join(data.moods) if data.moods else None
    t.notes = data.notes
    t.license_confirmed = data.license_confirmed
    session.commit()
    return t


def track_path(session: Session, settings: Settings, track_id: str) -> Path:
    t = get_track(session, track_id)
    p = settings.resolve_data_path(t.file_path)
    if not p.is_file():
        raise NotFoundError("Fichier audio absent : relancez l'analyse du dossier.")
    return p


def audio_assets(settings: Settings) -> list[AudioAssetOut]:
    models = settings.subdir("models")
    out = []
    for a in ALL_ASSETS.values():
        present = all((models / a.subdir / name).is_file() for name in a.files)
        out.append(
            AudioAssetOut(
                id=a.id,
                label=a.label,
                purpose=a.purpose,
                size_mb=a.size_mb,
                license=a.license,
                credit=a.credit,
                present=present,
                is_voice=a.id in PIPER_VOICES,
                language=a.id.split("_")[0] if a.id in PIPER_VOICES else None,
            )
        )
    return out
