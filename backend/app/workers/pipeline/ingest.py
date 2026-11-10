"""Étapes du job ``ingest_youtube``.

Chaque étape lit son entrée en base, écrit sa sortie (base + fichiers sous GSA_DATA_DIR)
et retourne un résumé JSON stocké dans ``job_steps.output_json``. Les étapes sont
idempotentes : relancées après une interruption, elles réutilisent un résultat valide.
"""

from __future__ import annotations

import json
import shutil
from typing import Any

from sqlalchemy import delete, select

from app.adapters.types import SourceMetadata
from app.models import Project, SourceMedia, Transcript, TranscriptSegment
from app.workers.context import StepContext
from app.workers.errors import StepError

PLACEHOLDER_PREFIX = "YouTube · "


def _source(ctx: StepContext, session) -> SourceMedia:  # type: ignore[no-untyped-def]
    source = session.scalar(select(SourceMedia).where(SourceMedia.project_id == ctx.project_id))
    if source is None:
        raise StepError("Aucune source associée à ce projet.")
    return source


def _project_dirs(ctx: StepContext) -> tuple:  # type: ignore[type-arg]
    return (
        ctx.settings.subdir("sources") / ctx.project_id,
        ctx.settings.subdir("projects") / ctx.project_id,
    )


# --------------------------------------------------------------------------- 1. validation


def validating_source(ctx: StepContext) -> dict[str, Any]:
    with ctx.session_factory() as s:
        url = _source(ctx, s).url
    ctx.report_progress(0.1, "Lecture des métadonnées YouTube…")
    meta: SourceMetadata = ctx.adapters.downloader.fetch_metadata(url)
    ctx.check_cancel()

    # Espace disque : estimation du fichier + marge de sécurité configurable.
    free = shutil.disk_usage(ctx.settings.data_dir).free
    needed = int((meta.estimated_size_bytes or 0) * 1.3) + int(ctx.settings.min_free_disk_gb * 1e9)
    if free < needed:
        raise StepError(
            f"Espace disque insuffisant sur {ctx.settings.data_dir} : {free / 1e9:.1f} Go libres, "
            f"{needed / 1e9:.1f} Go nécessaires (vidéo + marge GSA_MIN_FREE_DISK_GB)."
        )

    with ctx.session_factory() as s:
        source = _source(ctx, s)
        source.title = meta.title
        source.uploader = meta.uploader
        source.channel_id = meta.channel_id
        source.channel_url = meta.channel_url
        source.upload_date = meta.upload_date
        source.duration_seconds = meta.duration_seconds
        source.platform_license = meta.platform_license
        source.metadata_json = json.dumps(meta.raw, ensure_ascii=False, default=str)
        project = s.get(Project, ctx.project_id)
        if project and meta.title and project.name.startswith(PLACEHOLDER_PREFIX):
            project.name = meta.title[:200]
        s.commit()
    return {
        "title": meta.title,
        "duration_seconds": meta.duration_seconds,
        "estimated_size_bytes": meta.estimated_size_bytes,
        "platform_license": meta.platform_license,
    }


# --------------------------------------------------------------------------- 2. téléchargement


def downloading(ctx: StepContext) -> dict[str, Any]:
    sources_dir, _ = _project_dirs(ctx)
    with ctx.session_factory() as s:
        source = _source(ctx, s)
        url, existing = source.url, source.media_path
    if existing:
        path = ctx.settings.resolve_data_path(existing)
        if path.is_file() and path.stat().st_size > 0:
            return {"media_path": existing, "reused": True}

    path = ctx.adapters.downloader.download(url, sources_dir, ctx.report_progress, ctx.check_cancel)
    relative = ctx.settings.to_relative(path)
    size = path.stat().st_size
    with ctx.session_factory() as s:
        source = _source(ctx, s)
        source.media_path = relative
        source.media_size_bytes = size
        s.commit()
    return {"media_path": relative, "size_bytes": size}


# --------------------------------------------------------------------------- 3. ffprobe


def probing_media(ctx: StepContext) -> dict[str, Any]:
    with ctx.session_factory() as s:
        media_path = _source(ctx, s).media_path
    if not media_path:
        raise StepError("Aucun fichier vidéo téléchargé à analyser.")
    probe = ctx.adapters.media.probe(ctx.settings.resolve_data_path(media_path))
    if not probe.has_video:
        raise StepError("Le fichier ne contient aucune piste vidéo.")
    if not probe.has_audio:
        raise StepError(
            "La vidéo ne contient pas de piste audio : la transcription est impossible."
        )
    if probe.duration_seconds <= 0:
        raise StepError("Durée de la vidéo illisible (fichier tronqué ?).")
    with ctx.session_factory() as s:
        source = _source(ctx, s)
        source.width, source.height, source.fps = probe.width, probe.height, probe.fps
        source.video_codec, source.audio_codec = probe.video_codec, probe.audio_codec
        source.has_audio = probe.has_audio
        source.probe_json = json.dumps(probe.raw, ensure_ascii=False)
        # La durée réelle du fichier fait foi sur celle annoncée par la plateforme.
        source.duration_seconds = probe.duration_seconds
        s.commit()
    return probe.model_dump(exclude={"raw"})


# --------------------------------------------------------------------------- 4. audio


def extracting_audio(ctx: StepContext) -> dict[str, Any]:
    _, project_dir = _project_dirs(ctx)
    dst = project_dir / "audio_16k_mono.wav"
    with ctx.session_factory() as s:
        source = _source(ctx, s)
        media_path, duration = source.media_path, source.duration_seconds or 0.0
    if not media_path:
        raise StepError("Aucun fichier vidéo dont extraire l'audio.")

    media = ctx.adapters.media
    if dst.is_file():  # reprise : réutiliser un WAV complet
        try:
            existing = media.probe(dst)
            if abs(existing.duration_seconds - duration) < 1.0:
                return _save_audio(ctx, dst, reused=True)
        except StepError:
            pass
    media.extract_audio(
        ctx.settings.resolve_data_path(media_path),
        dst,
        duration,
        ctx.report_progress,
        ctx.check_cancel,
    )
    return _save_audio(ctx, dst, reused=False)


def _save_audio(ctx: StepContext, dst, *, reused: bool) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    relative = ctx.settings.to_relative(dst)
    with ctx.session_factory() as s:
        _source(ctx, s).audio_path = relative
        s.commit()
    return {"audio_path": relative, "size_bytes": dst.stat().st_size, "reused": reused}


# --------------------------------------------------------------------------- 5. transcription


def transcribing(ctx: StepContext) -> dict[str, Any]:
    with ctx.session_factory() as s:
        source = _source(ctx, s)
        audio_path, source_id = source.audio_path, source.id
    if not audio_path:
        raise StepError("Aucun fichier audio à transcrire.")

    result = ctx.adapters.transcriber.transcribe(
        ctx.settings.resolve_data_path(audio_path), ctx.report_progress, ctx.check_cancel
    )
    ctx.check_cancel()

    with ctx.session_factory() as s:
        # Une nouvelle transcription source remplace la précédente (relance).
        s.execute(
            delete(Transcript).where(
                Transcript.source_media_id == source_id, Transcript.kind == "source"
            )
        )
        transcript = Transcript(
            source_media_id=source_id,
            kind="source",
            engine=result.engine,
            model=result.model,
            device=result.device,
            compute_type=result.compute_type,
            language=result.language,
            language_probability=result.language_probability,
            audio_duration_seconds=result.audio_duration_seconds,
            processing_seconds=result.processing_seconds,
            options_json=json.dumps(result.options, ensure_ascii=False),
        )
        transcript.segments = [
            TranscriptSegment(
                position=i,
                start_seconds=seg.start,
                end_seconds=seg.end,
                text=seg.text,
                avg_logprob=seg.avg_logprob,
                no_speech_prob=seg.no_speech_prob,
                words_json=json.dumps([w.model_dump() for w in seg.words], ensure_ascii=False),
            )
            for i, seg in enumerate(result.segments)
        ]
        s.add(transcript)
        s.commit()
        transcript_id = transcript.id

    speed = (
        result.audio_duration_seconds / result.processing_seconds
        if result.processing_seconds
        else None
    )
    return {
        "transcript_id": transcript_id,
        "segments": len(result.segments),
        "words": sum(len(seg.words) for seg in result.segments),
        "language": result.language,
        "language_probability": result.language_probability,
        "engine": result.engine,
        "model": result.model,
        "device": result.device,
        "compute_type": result.compute_type,
        "audio_duration_seconds": result.audio_duration_seconds,
        "model_load_seconds": result.model_load_seconds,
        "processing_seconds": result.processing_seconds,
        "realtime_factor": round(speed, 2) if speed else None,
        "vram_baseline_used_mib": result.vram_baseline_used_mib,
        "vram_peak_used_mib": result.vram_peak_used_mib,
        "warnings": result.warnings,
    }


INGEST_STEPS = {
    "validating_source": validating_source,
    "downloading": downloading,
    "probing_media": probing_media,
    "extracting_audio": extracting_audio,
    "transcribing": transcribing,
}
