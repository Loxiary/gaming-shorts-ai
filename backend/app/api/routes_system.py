from __future__ import annotations

import shutil
from datetime import timedelta
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.api.deps import get_session, get_settings_dep
from app.core.config import APP_NAME, APP_PHASE, APP_VERSION, DATA_SUBDIRS, Settings
from app.core.errors import AppError
from app.db.session import ensure_database_ready
from app.schemas.api import (
    DataDirOut,
    FeatureStatusOut,
    HealthOut,
    SystemInfoOut,
    ToolStatusOut,
    WorkerStatusOut,
)
from app.services.queue import worker_status

router = APIRouter(prefix="/api", tags=["system"])

# Ce que l'application sait réellement faire à ce stade (affiché tel quel dans l'UI).
FEATURES = [
    FeatureStatusOut(name="Bibliothèque de projets", available=True, note="Disponible"),
    FeatureStatusOut(
        name="File d'attente persistante", available=True, note="Jobs de démonstration uniquement"
    ),
    FeatureStatusOut(name="Import de liens YouTube", available=False, note="Pas encore implémenté"),
    FeatureStatusOut(
        name="Transcription / analyse IA", available=False, note="Pas encore implémenté"
    ),
    FeatureStatusOut(
        name="Détection et score des clips", available=False, note="Pas encore implémenté"
    ),
    FeatureStatusOut(name="Montage et rendu vidéo", available=False, note="Pas encore implémenté"),
]


def _dir_size(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def _worker(request: Request) -> WorkerStatusOut:
    settings: Settings = request.app.state.settings
    session = request.app.state.session_factory()
    try:
        alive, hb = worker_status(session, timedelta(seconds=settings.worker_stale_seconds))
    finally:
        session.close()
    return WorkerStatusOut(
        alive=alive,
        last_seen_at=hb.last_seen_at if hb else None,
        worker_id=hb.worker_id if hb else None,
    )


@router.get("/health", response_model=HealthOut)
def health(request: Request) -> HealthOut:
    state = request.app.state
    try:
        ensure_database_ready(state.engine, state.settings)
        state.db_ready = True
        database, detail = "ok", None
    except AppError as exc:
        database, detail = "migration_required", exc.message
    worker = (
        _worker(request)
        if database == "ok"
        else WorkerStatusOut(alive=False, last_seen_at=None, worker_id=None)
    )
    return HealthOut(
        status="ok" if database == "ok" else "degraded",
        app=APP_NAME,
        version=APP_VERSION,
        phase=APP_PHASE,
        database=database,
        database_detail=detail,
        worker=worker,
    )


@router.get("/system", response_model=SystemInfoOut, dependencies=[Depends(get_session)])
def system_info(settings: Annotated[Settings, Depends(get_settings_dep)]) -> SystemInfoOut:
    usage = shutil.disk_usage(settings.data_dir)
    db_size = sum(
        p.stat().st_size for p in settings.data_dir.glob(settings.db_path.name + "*") if p.is_file()
    )
    tools = []
    for name in ("ffmpeg", "ffprobe"):
        found = shutil.which(name)
        tools.append(ToolStatusOut(name=name, found=found is not None, path=found))
    return SystemInfoOut(
        app=APP_NAME,
        version=APP_VERSION,
        phase=APP_PHASE,
        api_host=settings.api_host,
        api_port=settings.api_port,
        data_dir=str(settings.data_dir),
        database_path=str(settings.db_path),
        database_size_bytes=db_size,
        disk_total_bytes=usage.total,
        disk_free_bytes=usage.free,
        data_dirs=[
            DataDirOut(
                name=name,
                path=str(settings.subdir(name)),
                exists=settings.subdir(name).exists(),
                size_bytes=_dir_size(settings.subdir(name)),
            )
            for name in DATA_SUBDIRS
        ],
        tools=tools,
        features=FEATURES,
        demo_step_seconds=settings.demo_step_seconds,
        worker_stale_seconds=settings.worker_stale_seconds,
    )
