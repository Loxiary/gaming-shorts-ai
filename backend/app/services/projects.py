"""Bibliothèque de projets : opérations CRUD."""

from __future__ import annotations

import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.models import Job, JobStatus, Project
from app.schemas.api import JobCounts, ProjectCreate, ProjectUpdate

logger = logging.getLogger(__name__)


def get_project(session: Session, project_id: str) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise NotFoundError(f"Projet introuvable : {project_id}")
    return project


def list_projects(session: Session) -> list[Project]:
    return list(session.scalars(select(Project).order_by(Project.created_at.desc())))


def job_counts_by_project(session: Session, project_ids: list[str]) -> dict[str, JobCounts]:
    counts: dict[str, JobCounts] = {pid: JobCounts() for pid in project_ids}
    if not project_ids:
        return counts
    rows = session.execute(
        select(Job.project_id, Job.status, func.count())
        .where(Job.project_id.in_(project_ids))
        .group_by(Job.project_id, Job.status)
    )
    for project_id, status, count in rows:
        bucket = counts[project_id]
        setattr(bucket, status, count)
        bucket.total += count
    return counts


def create_project(session: Session, data: ProjectCreate) -> Project:
    project = Project(
        name=data.name, game=data.game, description=data.description, is_test=data.is_test
    )
    session.add(project)
    session.commit()
    logger.info("Projet créé", extra={"project_id": project.id})
    return project


def update_project(session: Session, project_id: str, data: ProjectUpdate) -> Project:
    project = get_project(session, project_id)
    changes = data.model_dump(exclude_unset=True)
    if "name" in changes and changes["name"] is None:
        raise ConflictError("Le nom du projet ne peut pas être supprimé")
    for field, value in changes.items():
        setattr(project, field, value)
    session.commit()
    logger.info("Projet modifié", extra={"project_id": project.id})
    return project


def delete_project(session: Session, project_id: str) -> None:
    project = get_project(session, project_id)
    running = session.scalar(
        select(func.count())
        .select_from(Job)
        .where(Job.project_id == project_id, Job.status == JobStatus.RUNNING)
    )
    if running:
        raise ConflictError(
            "Impossible de supprimer un projet dont un job est en cours. Annulez-le d'abord."
        )
    session.delete(project)
    session.commit()
    logger.info("Projet supprimé", extra={"project_id": project_id})
