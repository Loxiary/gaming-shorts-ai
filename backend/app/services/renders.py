"""Rendus de shorts : création, lecture, export confirmé, suppression."""

from __future__ import annotations

import json
import logging
import re
import shutil
import unicodedata
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError, ConflictError, NotFoundError
from app.core.time import utcnow
from app.models import (
    ACTIVE_JOB_STATUSES,
    ClipAnalysis,
    ClipCandidate,
    ClipRender,
    Job,
    JobStatus,
)
from app.render.risk import export_warnings
from app.schemas.render import RenderOut
from app.services import profiles as profile_svc
from app.services.analyses import candidate_to_out
from app.services.queue import enqueue_job
from app.services.sources import get_source

logger = logging.getLogger(__name__)


def _loads(value: str | None, default: Any) -> Any:
    return json.loads(value) if value else default


def create_render(session: Session, candidate_id: str, profile_id: str | None) -> ClipRender:
    candidate = session.get(ClipCandidate, candidate_id)
    if candidate is None:
        raise NotFoundError("Extrait introuvable.")
    analysis = candidate.analysis
    if candidate.status not in {"scored", "signals_only"}:
        raise AppError("Cet extrait n'a pas été évalué : il ne peut pas être monté.")
    active = session.scalar(
        select(ClipRender.id)
        .join(Job, Job.id == ClipRender.job_id)
        .where(
            ClipRender.candidate_id == candidate_id,
            Job.status.in_(ACTIVE_JOB_STATUSES),
        )
    )
    if active:
        raise ConflictError("Un montage de cet extrait est déjà en attente ou en cours.")
    if profile_id:
        profile_snapshot = profile_svc.snapshot(profile_svc.get_profile(session, profile_id))
    elif analysis.profile_id and (
        p := session.get(profile_svc.EditingProfile, analysis.profile_id)
    ):
        profile_snapshot = profile_svc.snapshot(p)  # réglages ACTUELS du profil de l'analyse
    else:
        profile_snapshot = json.loads(analysis.profile_snapshot_json)

    job = enqueue_job(session, analysis.project_id, "render_clip", internal=True)
    render = ClipRender(
        project_id=analysis.project_id,
        candidate_id=candidate.id,
        job_id=job.id,
        start_seconds=candidate.start_seconds,
        end_seconds=candidate.end_seconds,
        profile_snapshot_json=json.dumps(profile_snapshot, ensure_ascii=False),
        candidate_snapshot_json=candidate_to_out(candidate).model_dump_json(),
    )
    session.add(render)
    session.commit()
    logger.info("Montage demandé", extra={"project_id": analysis.project_id, "job_id": job.id})
    return render


def create_renders_for_selection(
    session: Session, analysis_id: str, profile_id: str | None
) -> tuple[list[ClipRender], list[str]]:
    """Montage en lot des extraits SÉLECTIONNÉS d'une analyse. Un extrait déjà monté (ou en
    cours de montage) est ignoré, pour ne pas dépenser deux fois. Retourne (créés, ignorés)."""
    analysis = session.get(ClipAnalysis, analysis_id)
    if analysis is None:
        raise NotFoundError("Analyse introuvable.")
    candidates = list(
        session.scalars(
            select(ClipCandidate)
            .where(ClipCandidate.analysis_id == analysis_id, ClipCandidate.selected.is_(True))
            .order_by(ClipCandidate.start_seconds)
        )
    )
    if not candidates:
        raise AppError("Aucun extrait sélectionné dans cette analyse : rien à monter.")
    created: list[ClipRender] = []
    skipped: list[str] = []
    for c in candidates:
        existing = session.scalar(
            select(ClipRender.id)
            .outerjoin(Job, Job.id == ClipRender.job_id)
            .where(
                ClipRender.candidate_id == c.id,
                (Job.status.is_(None))
                | Job.status.in_((*ACTIVE_JOB_STATUSES, JobStatus.COMPLETED)),
            )
        )
        if existing:
            skipped.append(c.id)
            continue
        created.append(create_render(session, c.id, profile_id))
    return created, skipped


def get_render(session: Session, render_id: str) -> ClipRender:
    render = session.get(ClipRender, render_id)
    if render is None:
        raise NotFoundError(f"Rendu introuvable : {render_id}")
    return render


def list_renders(
    session: Session, project_id: str | None = None, exported_only: bool = False
) -> list[ClipRender]:
    stmt = select(ClipRender).order_by(ClipRender.created_at.desc())
    if project_id:
        stmt = stmt.where(ClipRender.project_id == project_id)
    if exported_only:
        stmt = stmt.where(ClipRender.export_status == "exported")
    return list(session.scalars(stmt))


def _file_ok(settings: Settings, relative: str | None) -> bool:
    if not relative:
        return False
    try:
        return settings.resolve_data_path(relative).is_file()
    except ValueError:
        return False


def render_to_out(session: Session, settings: Settings, r: ClipRender) -> RenderOut:
    job = session.get(Job, r.job_id) if r.job_id else None
    profile = _loads(r.profile_snapshot_json, {})
    risk = _loads(r.risk_report_json, None)
    qc = _loads(r.qc_json, None)
    ready = bool(
        job
        and job.status == JobStatus.COMPLETED
        and r.qc_passed
        and _file_ok(settings, r.output_path)
    )
    return RenderOut(
        id=r.id,
        project_id=r.project_id,
        candidate_id=r.candidate_id,
        job_id=r.job_id,
        job_status=job.status if job else None,
        job_error=job.error_message if job else None,
        start_seconds=r.start_seconds,
        end_seconds=r.end_seconds,
        duration_seconds=round(r.end_seconds - r.start_seconds, 2),
        profile_name=profile.get("name", "?"),
        plan=_loads(r.plan_json, None),
        plan_engine=r.plan_engine,
        subtitles=_loads(r.subtitles_json, []),
        subtitle_language=r.subtitle_language,
        subtitles_are_translation=r.subtitles_are_translation,
        video_url=f"/api/renders/{r.id}/video" if _file_ok(settings, r.output_path) else None,
        output_size_bytes=r.output_size_bytes,
        qc=qc,
        qc_passed=r.qc_passed,
        risk_report=risk,
        audio_report=_loads(r.audio_report_json, None),
        facecam=_loads(r.facecam_json, None),
        credits=_loads(r.credits_json, []),
        preview_audio_url=(
            f"/api/renders/{r.id}/audio-preview"
            if _file_ok(settings, r.preview_audio_path)
            else None
        ),
        export_warnings=export_warnings(risk, qc) if risk else [],
        files_purged=r.files_purged,
        ready=ready,
        cost_usd=round(r.cost_usd, 4),
        export_status=r.export_status,
        exported_path=str(settings.resolve_data_path(r.exported_path)) if r.exported_path else None,
        export_confirmed_at=r.export_confirmed_at,
        acknowledged_warnings=_loads(r.acknowledged_warnings_json, []),
        created_at=r.created_at,
    )


def video_path(session: Session, settings: Settings, render_id: str) -> Path:
    r = get_render(session, render_id)
    if not _file_ok(settings, r.output_path):
        raise NotFoundError("Fichier vidéo du rendu non disponible.")
    return settings.resolve_data_path(r.output_path or "")


def preview_audio_path(session: Session, settings: Settings, render_id: str) -> Path:
    r = get_render(session, render_id)
    if not _file_ok(settings, r.preview_audio_path):
        raise NotFoundError("Aperçu audio non disponible.")
    return settings.resolve_data_path(r.preview_audio_path or "")


def _slug(text: str, limit: int = 50) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    return text[:limit].rstrip("-") or "short"


def confirm_export(
    session: Session, settings: Settings, render_id: str, acknowledged: bool
) -> ClipRender:
    """Export après confirmation EXPLICITE. Les avertissements de risque ne bloquent jamais ;
    seul un fichier techniquement invalide (contrôle qualité critique) ne peut être exporté."""
    r = get_render(session, render_id)
    if not acknowledged:
        raise AppError("Confirmez avoir lu les avertissements avant d'exporter.")
    if r.export_status == "exported":
        raise ConflictError("Ce short a déjà été exporté.")
    job = session.get(Job, r.job_id) if r.job_id else None
    if not job or job.status != JobStatus.COMPLETED or not r.qc_passed:
        raise ConflictError(
            "Ce rendu n'est pas prêt : le montage n'est pas terminé ou le fichier a échoué au "
            "contrôle qualité (voir le détail du contrôle)."
        )
    src = video_path(session, settings, render_id)
    source = get_source(session, r.project_id)
    title = source.title if source and source.title else "short"
    name = f"{utcnow():%Y%m%d-%H%M}_{_slug(title)}_{int(r.start_seconds)}s"
    dest_dir = settings.subdir("exports")
    dest = dest_dir / f"{name}.mp4"
    n = 2
    while dest.exists():
        dest, n = dest_dir / f"{name}-{n}.mp4", n + 1
    tmp = dest.with_suffix(".part")
    shutil.copyfile(src, tmp)
    tmp.replace(dest)

    risk = _loads(r.risk_report_json, {})
    qc = _loads(r.qc_json, {})
    warnings = export_warnings(risk, qc) if risk else []
    sidecar = {
        "file": dest.name,
        "exported_at": utcnow().isoformat(),
        "source": risk.get("source"),
        "rights": risk.get("rights"),
        "excerpt": {"start_seconds": r.start_seconds, "end_seconds": r.end_seconds},
        "plan": _loads(r.plan_json, None),
        "subtitles": {
            "language": r.subtitle_language,
            "is_translation": r.subtitles_are_translation,
        },
        "audio": _loads(r.audio_report_json, None),
        "facecam": _loads(r.facecam_json, None),
        "credits": _loads(r.credits_json, []),
        "quality_check": qc,
        "risk_report": risk,
        "acknowledged_warnings": warnings,
        "note": "Export confirmé par l'utilisateur après lecture des avertissements.",
    }
    dest.with_suffix(".json").write_text(
        json.dumps(sidecar, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    r.export_status = "exported"
    r.exported_path = settings.to_relative(dest)
    r.export_confirmed_at = utcnow()
    r.acknowledged_warnings_json = json.dumps(warnings, ensure_ascii=False)
    session.commit()
    logger.info("Short exporté : %s", dest.name, extra={"project_id": r.project_id})
    return r


def delete_render(session: Session, settings: Settings, render_id: str) -> None:
    """Supprime le rendu et ses fichiers de travail. Un fichier exporté est CONSERVÉ."""
    r = get_render(session, render_id)
    job = session.get(Job, r.job_id) if r.job_id else None
    if job and job.status in ACTIVE_JOB_STATUSES:
        raise ConflictError("Montage en cours : annulez-le d'abord.")
    workdir = settings.subdir("projects") / r.project_id / "renders" / r.id
    root = settings.data_dir.resolve()
    if workdir.resolve().is_relative_to(root) and workdir.is_dir():
        shutil.rmtree(workdir)
    session.delete(r)
    session.commit()
