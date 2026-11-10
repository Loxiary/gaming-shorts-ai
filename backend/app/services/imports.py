"""Import de liens : un projet + une source + un job d'ingestion par lien valide.

L'import est partiel : chaque lien est traité indépendamment et reçoit un résultat.
Le statut des droits est une DÉCLARATION informative de l'utilisateur ; il ne bloque jamais.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Project, SourceMedia
from app.schemas.api import ImportRequest, ImportResultItem
from app.services.queue import enqueue_job
from app.services.source_urls import InvalidSourceUrl, parse_source_url
from app.workers.pipeline.ingest import PLACEHOLDER_PREFIX

logger = logging.getLogger(__name__)


def import_sources(session: Session, request: ImportRequest) -> list[ImportResultItem]:
    results: list[ImportResultItem] = []
    seen: set[str] = set()
    for raw in request.urls:
        try:
            parsed = parse_source_url(raw)
        except InvalidSourceUrl as exc:
            results.append(ImportResultItem(url=raw, status="rejected", message=str(exc)))
            continue
        if parsed.external_id in seen:
            results.append(
                ImportResultItem(
                    url=raw, status="rejected", message="Lien en double dans la liste."
                )
            )
            continue
        seen.add(parsed.external_id)

        existing = session.scalar(
            select(SourceMedia).where(
                SourceMedia.source_type == parsed.source_type,
                SourceMedia.external_id == parsed.external_id,
            )
        )
        if existing is not None:
            results.append(
                ImportResultItem(
                    url=raw,
                    status="duplicate",
                    project_id=existing.project_id,
                    message="Cette vidéo est déjà dans la bibliothèque.",
                )
            )
            continue

        project = Project(
            name=f"{PLACEHOLDER_PREFIX}{parsed.external_id}",
            game=request.game,
            description=None,
            is_test=False,
        )
        project.source = SourceMedia(
            source_type=parsed.source_type,
            url=parsed.canonical_url,
            external_id=parsed.external_id,
            rights_status=request.rights_status,
            rights_note=request.rights_note,
        )
        session.add(project)
        try:
            session.commit()
        except IntegrityError:  # import concurrent de la même vidéo
            session.rollback()
            results.append(
                ImportResultItem(
                    url=raw,
                    status="duplicate",
                    message="Cette vidéo est déjà dans la bibliothèque.",
                )
            )
            continue
        job = enqueue_job(session, project.id, "ingest_youtube")
        logger.info(
            "Source importée", extra={"project_id": project.id, "job_id": job.id, "kind": job.kind}
        )
        results.append(
            ImportResultItem(url=raw, status="created", project_id=project.id, job_id=job.id)
        )
    return results
