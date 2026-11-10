from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.core.errors import AppError
from app.schemas.api import ProjectCreate, ProjectDetailOut, ProjectOut, ProjectUpdate
from app.services import projects as svc
from app.services.queue import job_to_out

router = APIRouter(prefix="/api/projects", tags=["projects"])
SessionDep = Annotated[Session, Depends(get_session)]


def _to_out(session: Session, project) -> ProjectOut:
    counts = svc.job_counts_by_project(session, [project.id])[project.id]
    return ProjectOut.model_validate(project).model_copy(update={"job_counts": counts})


@router.get("", response_model=list[ProjectOut])
def list_projects(session: SessionDep) -> list[ProjectOut]:
    projects = svc.list_projects(session)
    counts = svc.job_counts_by_project(session, [p.id for p in projects])
    return [
        ProjectOut.model_validate(p).model_copy(update={"job_counts": counts[p.id]})
        for p in projects
    ]


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(data: ProjectCreate, session: SessionDep) -> ProjectOut:
    return _to_out(session, svc.create_project(session, data))


@router.get("/{project_id}", response_model=ProjectDetailOut)
def get_project(project_id: str, session: SessionDep) -> ProjectDetailOut:
    project = svc.get_project(session, project_id)
    base = _to_out(session, project)
    return ProjectDetailOut(**base.model_dump(), jobs=[job_to_out(j) for j in project.jobs])


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project(project_id: str, data: ProjectUpdate, session: SessionDep) -> ProjectOut:
    return _to_out(session, svc.update_project(session, project_id, data))


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: str,
    session: SessionDep,
    confirm: Annotated[
        bool, Query(description="Doit valoir true (confirmation explicite)")
    ] = False,
) -> Response:
    if not confirm:
        raise AppError("Suppression non confirmée : ajouter ?confirm=true.")
    svc.delete_project(session, project_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
