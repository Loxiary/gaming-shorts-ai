from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_session, get_settings_dep
from app.core.config import Settings
from app.core.errors import AppError
from app.models import Project
from app.schemas.api import (
    ImportRequest,
    ImportResultItem,
    ProjectCreate,
    ProjectDetailOut,
    ProjectOut,
    ProjectUpdate,
    SourceOut,
    SourceUpdate,
    TranscriptOut,
)
from app.services import projects as svc
from app.services import sources as src
from app.services.imports import import_sources
from app.services.queue import job_to_out

router = APIRouter(prefix="/api", tags=["projects"])
SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings_dep)]


def _to_out(session: Session, project: Project) -> ProjectOut:
    counts = svc.job_counts_by_project(session, [project.id])[project.id]
    return ProjectOut.model_validate(project).model_copy(update={"job_counts": counts})


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(session: SessionDep) -> list[ProjectOut]:
    projects = svc.list_projects(session)
    counts = svc.job_counts_by_project(session, [p.id for p in projects])
    return [
        ProjectOut.model_validate(p).model_copy(update={"job_counts": counts[p.id]})
        for p in projects
    ]


@router.post("/projects", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(data: ProjectCreate, session: SessionDep) -> ProjectOut:
    return _to_out(session, svc.create_project(session, data))


@router.post("/imports", response_model=list[ImportResultItem])
def create_import(data: ImportRequest, session: SessionDep) -> list[ImportResultItem]:
    """Importe un ou plusieurs liens. Chaque lien reçoit son propre résultat."""
    return import_sources(session, data)


@router.get("/projects/{project_id}", response_model=ProjectDetailOut)
def get_project(project_id: str, session: SessionDep, settings: SettingsDep) -> ProjectDetailOut:
    project = svc.get_project(session, project_id)
    base = _to_out(session, project)
    for job in project.jobs:
        _ = job.steps  # chargement des étapes : libellé de l'étape courante
    source = src.get_source(session, project_id)
    transcript = src.latest_transcript(session, source.id) if source else None
    return ProjectDetailOut(
        **base.model_dump(),
        jobs=[job_to_out(j) for j in project.jobs],
        source=src.source_to_out(source, settings) if source else None,
        transcript=src.transcript_summary(session, transcript) if transcript else None,
        files_size_bytes=src.project_files_size(settings, project_id),
    )


@router.patch("/projects/{project_id}", response_model=ProjectOut)
def update_project(project_id: str, data: ProjectUpdate, session: SessionDep) -> ProjectOut:
    return _to_out(session, svc.update_project(session, project_id, data))


@router.patch("/projects/{project_id}/source", response_model=SourceOut)
def update_source(
    project_id: str, data: SourceUpdate, session: SessionDep, settings: SettingsDep
) -> SourceOut:
    """Met à jour la déclaration de droits (informative, ne bloque aucun traitement)."""
    return src.source_to_out(src.update_source(session, project_id, data), settings)


@router.get("/projects/{project_id}/transcript", response_model=TranscriptOut)
def get_transcript(project_id: str, session: SessionDep) -> TranscriptOut:
    svc.get_project(session, project_id)
    return src.get_transcript(session, project_id)


@router.get("/projects/{project_id}/media", response_class=FileResponse)
def get_media(project_id: str, session: SessionDep, settings: SettingsDep) -> FileResponse:
    """Vidéo source pour la prévisualisation locale (requêtes Range prises en charge)."""
    path = src.media_file(session, settings, project_id)
    return FileResponse(path, media_type="video/mp4" if path.suffix == ".mp4" else None)


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: str,
    session: SessionDep,
    settings: SettingsDep,
    confirm: Annotated[
        bool, Query(description="Doit valoir true (confirmation explicite)")
    ] = False,
) -> Response:
    if not confirm:
        raise AppError("Suppression non confirmée : ajouter ?confirm=true.")
    svc.delete_project(session, project_id)
    src.delete_project_files(settings, project_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
