"""File d'attente persistante (SQLite).

Garanties :
- un job n'est réclamé que par un seul worker (UPDATE conditionnel atomique) ;
- un seul job actif d'un même type par projet (index unique partiel) ;
- les étapes terminées ne sont jamais rejouées lors d'une reprise ou d'une relance ;
- un job « running » dont le worker ne donne plus signe de vie est remis en file.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.errors import AppError, ConflictError, NotFoundError
from app.core.time import utcnow
from app.models import (
    ACTIVE_JOB_STATUSES,
    Job,
    JobStatus,
    JobStep,
    SourceMedia,
    StepStatus,
    WorkerHeartbeat,
)
from app.schemas.api import JobDetailOut, JobOut, JobStepOut
from app.services.job_kinds import get_job_kind
from app.services.projects import get_project

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- lecture


def get_job(session: Session, job_id: str, *, with_steps: bool = False) -> Job:
    stmt = select(Job).where(Job.id == job_id).options(selectinload(Job.project))
    if with_steps:
        stmt = stmt.options(selectinload(Job.steps))
    job = session.scalar(stmt)
    if job is None:
        raise NotFoundError(f"Job introuvable : {job_id}")
    return job


def list_jobs(
    session: Session, *, status: str | None = None, project_id: str | None = None, limit: int = 200
) -> list[Job]:
    stmt = (
        select(Job)
        .options(selectinload(Job.project), selectinload(Job.steps))
        .order_by(Job.created_at.desc())
    )
    if status:
        stmt = stmt.where(Job.status == status)
    if project_id:
        stmt = stmt.where(Job.project_id == project_id)
    return list(session.scalars(stmt.limit(limit)))


def job_to_out(job: Job) -> JobOut:
    kind = get_job_kind(job.kind)
    current = None
    if job.current_step and "steps" in job.__dict__:  # étapes déjà chargées : pas de requête
        current = next((st for st in job.steps if st.name == job.current_step), None)
    return JobOut(
        id=job.id,
        project_id=job.project_id,
        project_name=job.project.name,
        kind=job.kind,
        kind_label=kind.label if kind else job.kind,
        is_demo=kind.is_demo if kind else False,
        status=job.status,
        progress=job.progress,
        current_step=job.current_step,
        current_step_label=current.label if current else None,
        current_step_detail=current.detail if current else None,
        error_message=job.error_message,
        cancel_requested=job.cancel_requested,
        attempts=job.attempts,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        updated_at=job.updated_at,
    )


def job_to_detail(job: Job) -> JobDetailOut:
    return JobDetailOut(
        **job_to_out(job).model_dump(),
        steps=[JobStepOut.model_validate(s) for s in job.steps],
    )


# --------------------------------------------------------------------------- commandes


def enqueue_job(session: Session, project_id: str, kind: str) -> Job:
    get_project(session, project_id)
    definition = get_job_kind(kind)
    if definition is None:
        raise AppError(f"Type de job inconnu : {kind}")
    if kind == "ingest_youtube":
        has_source = session.scalar(
            select(SourceMedia.id).where(SourceMedia.project_id == project_id)
        )
        if not has_source:
            raise AppError("Ce projet n'a pas de source : utilisez la page « Importer ».")

    active = session.scalar(
        select(Job.id).where(
            Job.project_id == project_id, Job.kind == kind, Job.status.in_(ACTIVE_JOB_STATUSES)
        )
    )
    if active:
        raise ConflictError(
            f"Un job « {definition.label} » est déjà en attente ou en cours pour ce projet."
        )

    job = Job(project_id=project_id, kind=kind, status=JobStatus.QUEUED)
    job.steps = [
        JobStep(position=i, name=s.name, label=s.label, status=StepStatus.PENDING)
        for i, s in enumerate(definition.steps)
    ]
    session.add(job)
    try:
        session.commit()
    except IntegrityError as exc:  # course entre deux requêtes simultanées
        session.rollback()
        raise ConflictError(
            f"Un job « {definition.label} » est déjà en attente ou en cours pour ce projet."
        ) from exc
    logger.info(
        "Job ajouté à la file", extra={"job_id": job.id, "project_id": project_id, "kind": kind}
    )
    return get_job(session, job.id, with_steps=True)


def request_cancel(session: Session, job_id: str) -> Job:
    now = utcnow()
    get_job(session, job_id)

    # Job en attente : annulation immédiate (conditionnelle pour éviter une course avec le worker).
    result = session.execute(
        update(Job)
        .where(Job.id == job_id, Job.status == JobStatus.QUEUED)
        .values(status=JobStatus.CANCELLED, finished_at=now, updated_at=now, current_step=None)
    )
    if result.rowcount:
        session.execute(
            update(JobStep)
            .where(JobStep.job_id == job_id, JobStep.status == StepStatus.PENDING)
            .values(status=StepStatus.CANCELLED)
        )
        session.commit()
        logger.info("Job annulé (en attente)", extra={"job_id": job_id})
        return get_job(session, job_id, with_steps=True)

    # Job en cours : annulation sûre à la fin de l'étape courante, par le worker.
    result = session.execute(
        update(Job)
        .where(Job.id == job_id, Job.status == JobStatus.RUNNING)
        .values(cancel_requested=True, updated_at=now)
    )
    session.commit()
    if not result.rowcount:
        raise ConflictError("Ce job est déjà terminé : il ne peut pas être annulé.")
    logger.info("Annulation demandée (job en cours)", extra={"job_id": job_id})
    session.expire_all()
    return get_job(session, job_id, with_steps=True)


def retry_job(session: Session, job_id: str) -> Job:
    """Remet en file un job échoué ou annulé ; les étapes terminées sont conservées."""
    now = utcnow()
    get_job(session, job_id)
    try:
        result = session.execute(
            update(Job)
            .where(Job.id == job_id, Job.status.in_((JobStatus.FAILED, JobStatus.CANCELLED)))
            .values(
                status=JobStatus.QUEUED,
                error_message=None,
                cancel_requested=False,
                finished_at=None,
                current_step=None,
                locked_by=None,
                updated_at=now,
            )
        )
        if not result.rowcount:
            session.rollback()
            raise ConflictError("Seul un job échoué ou annulé peut être relancé.")
        session.execute(
            update(JobStep)
            .where(JobStep.job_id == job_id, JobStep.status != StepStatus.COMPLETED)
            .values(
                status=StepStatus.PENDING, error_message=None, started_at=None, finished_at=None
            )
        )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise ConflictError(
            "Un job du même type est déjà en attente ou en cours pour ce projet."
        ) from exc
    logger.info("Job relancé", extra={"job_id": job_id})
    session.expire_all()
    return get_job(session, job_id, with_steps=True)


# --------------------------------------------------------------------------- worker


def claim_next_job(session: Session, worker_id: str) -> str | None:
    """Réclame atomiquement le plus ancien job en attente. Retourne son id ou None."""
    now = utcnow()
    oldest = (
        select(Job.id)
        .where(Job.status == JobStatus.QUEUED)
        .order_by(Job.created_at, Job.id)
        .limit(1)
        .scalar_subquery()
    )
    claimed = session.execute(
        update(Job)
        .where(Job.id == oldest, Job.status == JobStatus.QUEUED)
        .values(
            status=JobStatus.RUNNING,
            locked_by=worker_id,
            heartbeat_at=now,
            started_at=func.coalesce(Job.started_at, now),
            attempts=Job.attempts + 1,
            updated_at=now,
        )
        .returning(Job.id)
    ).scalar_one_or_none()
    session.commit()
    return claimed


def recover_stale_jobs(
    session: Session, stale_after: timedelta, now: datetime | None = None
) -> list[str]:
    """Remet en file les jobs « running » dont le worker ne donne plus signe de vie (crash)."""
    now = now or utcnow()
    limit = now - stale_after
    stale_ids = list(
        session.scalars(
            select(Job.id).where(
                Job.status == JobStatus.RUNNING,
                (Job.heartbeat_at.is_(None)) | (Job.heartbeat_at < limit),
            )
        )
    )
    if not stale_ids:
        return []
    session.execute(
        update(Job)
        .where(Job.id.in_(stale_ids), Job.status == JobStatus.RUNNING)
        .values(status=JobStatus.QUEUED, locked_by=None, current_step=None, updated_at=now)
    )
    session.execute(
        update(JobStep)
        .where(JobStep.job_id.in_(stale_ids), JobStep.status == StepStatus.RUNNING)
        .values(status=StepStatus.PENDING, started_at=None)
    )
    session.commit()
    for job_id in stale_ids:
        logger.warning(
            "Job abandonné remis en file (reprise après interruption)", extra={"job_id": job_id}
        )
    return stale_ids


def release_job(session: Session, job_id: str, worker_id: str) -> None:
    """Arrêt propre du worker : remet le job en file sans perdre les étapes terminées."""
    now = utcnow()
    result = session.execute(
        update(Job)
        .where(Job.id == job_id, Job.status == JobStatus.RUNNING, Job.locked_by == worker_id)
        .values(status=JobStatus.QUEUED, locked_by=None, current_step=None, updated_at=now)
    )
    if result.rowcount:
        session.execute(
            update(JobStep)
            .where(JobStep.job_id == job_id, JobStep.status == StepStatus.RUNNING)
            .values(status=StepStatus.PENDING, started_at=None)
        )
    session.commit()


def worker_status(session: Session, stale_after: timedelta) -> tuple[bool, WorkerHeartbeat | None]:
    latest = session.scalar(
        select(WorkerHeartbeat).order_by(WorkerHeartbeat.last_seen_at.desc()).limit(1)
    )
    if latest is None:
        return False, None
    return latest.last_seen_at >= utcnow() - stale_after, latest
