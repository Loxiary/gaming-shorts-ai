from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_session, get_settings_dep
from app.core.config import Settings
from app.core.errors import AppError
from app.schemas.render import BatchRenderOut, ExportConfirm, RenderCreate, RenderOut
from app.services import renders as svc
from app.services.projects import get_project

router = APIRouter(prefix="/api", tags=["render"])
SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings_dep)]


@router.post(
    "/candidates/{candidate_id}/renders",
    response_model=BatchRenderOut,
    status_code=status.HTTP_201_CREATED,
)
def create_render(
    candidate_id: str, data: RenderCreate, session: SessionDep, settings: SettingsDep
) -> BatchRenderOut:
    """Un short par public : version française seule si la source est en français, sinon
    version anglaise ET version française."""
    renders = svc.create_render(session, candidate_id, data.profile_id)
    return BatchRenderOut(
        created=[svc.render_to_out(session, settings, r) for r in renders],
        skipped_candidate_ids=[],
    )


@router.post(
    "/analyses/{analysis_id}/renders",
    response_model=BatchRenderOut,
    status_code=status.HTTP_201_CREATED,
)
def create_selection_renders(
    analysis_id: str, data: RenderCreate, session: SessionDep, settings: SettingsDep
) -> BatchRenderOut:
    """Monte tous les extraits sélectionnés (ceux déjà montés ou en cours sont ignorés)."""
    created, skipped = svc.create_renders_for_selection(session, analysis_id, data.profile_id)
    return BatchRenderOut(
        created=[svc.render_to_out(session, settings, r) for r in created],
        skipped_candidate_ids=skipped,
    )


@router.get("/projects/{project_id}/renders", response_model=list[RenderOut])
def list_project_renders(
    project_id: str, session: SessionDep, settings: SettingsDep
) -> list[RenderOut]:
    get_project(session, project_id)
    return [svc.render_to_out(session, settings, r) for r in svc.list_renders(session, project_id)]


@router.get("/renders/{render_id}", response_model=RenderOut)
def get_render(render_id: str, session: SessionDep, settings: SettingsDep) -> RenderOut:
    return svc.render_to_out(session, settings, svc.get_render(session, render_id))


@router.get("/renders/{render_id}/video", response_class=FileResponse)
def render_video(render_id: str, session: SessionDep, settings: SettingsDep) -> FileResponse:
    return FileResponse(svc.video_path(session, settings, render_id), media_type="video/mp4")


@router.get("/renders/{render_id}/audio-preview", response_class=FileResponse)
def render_audio_preview(
    render_id: str, session: SessionDep, settings: SettingsDep
) -> FileResponse:
    """Aperçu du mixage audio (niveau final), disponible avant la fin du rendu vidéo."""
    return FileResponse(
        svc.preview_audio_path(session, settings, render_id), media_type="audio/mp4"
    )


@router.post("/renders/{render_id}/confirm-export", response_model=RenderOut)
def confirm_export(
    render_id: str, data: ExportConfirm, session: SessionDep, settings: SettingsDep
) -> RenderOut:
    """Export après confirmation explicite. Les risques n'empêchent jamais l'export."""
    render = svc.confirm_export(session, settings, render_id, data.acknowledged)
    return svc.render_to_out(session, settings, render)


@router.delete("/renders/{render_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_render(
    render_id: str,
    session: SessionDep,
    settings: SettingsDep,
    confirm: Annotated[bool, Query(description="Doit valoir true")] = False,
) -> Response:
    if not confirm:
        raise AppError("Suppression non confirmée : ajouter ?confirm=true.")
    svc.delete_render(session, settings, render_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/exports", response_model=list[RenderOut])
def list_exports(session: SessionDep, settings: SettingsDep) -> list[RenderOut]:
    return [
        svc.render_to_out(session, settings, r)
        for r in svc.list_renders(session, exported_only=True)
    ]
