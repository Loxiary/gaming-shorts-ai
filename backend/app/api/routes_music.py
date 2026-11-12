from __future__ import annotations

import mimetypes
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_session, get_settings_dep
from app.core.config import Settings
from app.render.editorial import MUSIC_MOODS
from app.schemas.music import AudioStatusOut, MusicScanOut, MusicTrackIn, MusicTrackOut
from app.services import music as svc

router = APIRouter(prefix="/api", tags=["music"])
SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings_dep)]


@router.get("/music", response_model=list[MusicTrackOut])
def list_music(session: SessionDep) -> list[MusicTrackOut]:
    return [svc.to_out(t) for t in svc.list_tracks(session)]


@router.post("/music/scan", response_model=MusicScanOut)
def scan_music(session: SessionDep, settings: SettingsDep) -> MusicScanOut:
    """Analyse le dossier GSA_DATA_DIR/music (aucun téléchargement)."""
    return MusicScanOut(**svc.scan_library(session, settings))


@router.patch("/music/{track_id}", response_model=MusicTrackOut)
def update_music(track_id: str, data: MusicTrackIn, session: SessionDep) -> MusicTrackOut:
    return svc.to_out(svc.update_track(session, track_id, data))


@router.get("/music/{track_id}/audio", response_class=FileResponse)
def music_audio(track_id: str, session: SessionDep, settings: SettingsDep) -> FileResponse:
    path = svc.track_path(session, settings, track_id)
    return FileResponse(path, media_type=mimetypes.guess_type(path.name)[0] or "audio/mpeg")


@router.get("/audio/status", response_model=AudioStatusOut)
def audio_status(settings: SettingsDep) -> AudioStatusOut:
    """Modèles audio/facecam et voix installés, ambiances disponibles."""
    return AudioStatusOut(
        assets=svc.audio_assets(settings),
        moods=list(MUSIC_MOODS),
        music_folder=str(settings.subdir("music")),
        download_command="python -m app.cli.models download --all",
    )
