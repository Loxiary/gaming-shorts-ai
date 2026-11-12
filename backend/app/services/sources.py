"""Lecture/édition des sources et transcriptions d'un projet."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import Settings
from app.core.errors import NotFoundError
from app.models import SourceMedia, Transcript, TranscriptSegment
from app.schemas.api import SourceOut, SourceUpdate, TranscriptOut, TranscriptSummaryOut

logger = logging.getLogger(__name__)


def _exists(settings: Settings, relative: str | None) -> bool:
    if not relative:
        return False
    try:
        return settings.resolve_data_path(relative).is_file()
    except ValueError:
        return False


def get_source(session: Session, project_id: str) -> SourceMedia | None:
    return session.scalar(select(SourceMedia).where(SourceMedia.project_id == project_id))


def source_to_out(source: SourceMedia, settings: Settings) -> SourceOut:
    out = SourceOut.model_validate(source)
    return out.model_copy(
        update={
            "media_available": _exists(settings, source.media_path),
            "audio_available": _exists(settings, source.audio_path),
        }
    )


def update_source(session: Session, project_id: str, data: SourceUpdate) -> SourceMedia:
    source = get_source(session, project_id)
    if source is None:
        raise NotFoundError("Ce projet n'a pas de source.")
    for field, value in data.model_dump(exclude_unset=True).items():
        if field == "rights_status" and value is None:
            continue
        setattr(source, field, value)
    session.commit()
    logger.info("Droits de la source mis à jour", extra={"project_id": project_id})
    return source


def latest_transcript(session: Session, source_id: str) -> Transcript | None:
    return session.scalar(
        select(Transcript)
        .where(Transcript.source_media_id == source_id, Transcript.kind == "source")
        .order_by(Transcript.created_at.desc())
        .limit(1)
    )


def transcript_summary(session: Session, transcript: Transcript) -> TranscriptSummaryOut:
    count = session.scalar(
        select(func.count())
        .select_from(TranscriptSegment)
        .where(TranscriptSegment.transcript_id == transcript.id)
    )
    return TranscriptSummaryOut.model_validate(transcript).model_copy(
        update={"segment_count": count or 0}
    )


def get_transcript(session: Session, project_id: str) -> TranscriptOut:
    source = get_source(session, project_id)
    transcript = latest_transcript(session, source.id) if source else None
    if transcript is None:
        raise NotFoundError("Aucune transcription pour ce projet.")
    transcript = session.scalar(
        select(Transcript)
        .where(Transcript.id == transcript.id)
        .options(selectinload(Transcript.segments))
    )
    assert transcript is not None
    return TranscriptOut.model_validate(transcript).model_copy(
        update={"segment_count": len(transcript.segments)}
    )


def media_file(session: Session, settings: Settings, project_id: str) -> Path:
    source = get_source(session, project_id)
    if source is None or not _exists(settings, source.media_path):
        raise NotFoundError("Vidéo source non disponible.")
    assert source.media_path is not None
    return settings.resolve_data_path(source.media_path)


def project_file_dirs(settings: Settings, project_id: str) -> list[Path]:
    return [settings.subdir("sources") / project_id, settings.subdir("projects") / project_id]


def project_files_size(settings: Settings, project_id: str) -> int:
    return sum(
        f.stat().st_size
        for d in project_file_dirs(settings, project_id)
        if d.is_dir()
        for f in d.rglob("*")
        if f.is_file()
    )


def delete_project_files(settings: Settings, project_id: str) -> None:
    """Supprime les dossiers de fichiers d'un projet (uniquement sous GSA_DATA_DIR)."""
    root = settings.data_dir.resolve()
    for directory in project_file_dirs(settings, project_id):
        resolved = directory.resolve()
        if resolved.is_relative_to(root) and resolved != root and resolved.is_dir():
            shutil.rmtree(resolved)
            logger.info(
                "Fichiers du projet supprimés : %s", resolved, extra={"project_id": project_id}
            )
