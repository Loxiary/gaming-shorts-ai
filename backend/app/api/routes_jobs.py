from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.models import JobStatus
from app.schemas.api import JobCreate, JobDetailOut, JobKindOut, JobOut
from app.services import queue as svc
from app.services.job_kinds import JOB_KINDS

router = APIRouter(prefix="/api", tags=["jobs"])
SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/job-kinds", response_model=list[JobKindOut])
def list_job_kinds() -> list[JobKindOut]:
    return [
        JobKindOut(
            kind=k.kind,
            label=k.label,
            description=k.description,
            is_demo=k.is_demo,
            steps=[s.label for s in k.steps],
        )
        for k in JOB_KINDS.values()
    ]


@router.get("/jobs", response_model=list[JobOut])
def list_jobs(
    session: SessionDep,
    status_filter: Annotated[JobStatus | None, Query(alias="status")] = None,
    project_id: Annotated[str | None, Query(max_length=32)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> list[JobOut]:
    jobs = svc.list_jobs(session, status=status_filter, project_id=project_id, limit=limit)
    return [svc.job_to_out(j) for j in jobs]


@router.post("/jobs", response_model=JobDetailOut, status_code=status.HTTP_201_CREATED)
def create_job(data: JobCreate, session: SessionDep) -> JobDetailOut:
    return svc.job_to_detail(svc.enqueue_job(session, data.project_id, data.kind))


@router.get("/jobs/{job_id}", response_model=JobDetailOut)
def get_job(job_id: str, session: SessionDep) -> JobDetailOut:
    return svc.job_to_detail(svc.get_job(session, job_id, with_steps=True))


@router.post("/jobs/{job_id}/cancel", response_model=JobDetailOut)
def cancel_job(job_id: str, session: SessionDep) -> JobDetailOut:
    return svc.job_to_detail(svc.request_cancel(session, job_id))


@router.post("/jobs/{job_id}/pause", response_model=JobDetailOut)
def pause_job(job_id: str, session: SessionDep) -> JobDetailOut:
    """Pause sûre : immédiate si le job attend, sinon à la fin de l'étape en cours."""
    return svc.job_to_detail(svc.request_pause(session, job_id))


@router.post("/jobs/{job_id}/resume", response_model=JobDetailOut)
def resume_job(job_id: str, session: SessionDep) -> JobDetailOut:
    return svc.job_to_detail(svc.resume_job(session, job_id))


@router.post("/jobs/{job_id}/retry", response_model=JobDetailOut)
def retry_job(job_id: str, session: SessionDep) -> JobDetailOut:
    return svc.job_to_detail(svc.retry_job(session, job_id))
