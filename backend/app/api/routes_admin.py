"""Phase 6 : réglages globaux, stockage et nettoyage, sauvegardes, export/import des profils."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.deps import get_session, get_settings_dep
from app.core.config import Settings
from app.core.errors import AppError
from app.schemas.analysis import ProfileOut
from app.services import backup as backup_svc
from app.services import runtime_settings as rs
from app.services import storage as storage_svc
from app.services.profiles import to_out as profile_out

router = APIRouter(prefix="/api", tags=["admin"])
SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings_dep)]


# --------------------------------------------------------------------------- schémas


class RuntimeSettingOut(BaseModel):
    key: str
    label: str
    group: str
    help: str
    type: str
    choices: list[str]
    min: float | None
    max: float | None
    value: Any
    env_value: Any
    overridden: bool


class RuntimeSettingsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    values: dict[str, Any] = Field(description="null = rétablir la valeur du .env")


class ProjectUsageOut(BaseModel):
    project_id: str
    name: str
    source_bytes: int
    analysis_bytes: int
    renders_bytes: int
    total_bytes: int
    last_activity: datetime | None


class StorageOut(BaseModel):
    data_dir: str
    disk_total_bytes: int
    disk_free_bytes: int
    min_free_disk_gb: float
    directories: dict[str, int]
    database_bytes: int
    db_backups_bytes: int
    projects: list[ProjectUsageOut]
    retention: dict[str, Any]
    categories: dict[str, str]


class CleanupIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    categories: list[str] = Field(min_length=1)
    dry_run: bool = True


class CleanupItemOut(BaseModel):
    category: str
    path: str
    bytes: int
    reason: str
    project_id: str | None


class CleanupOut(BaseModel):
    dry_run: bool
    categories: list[str]
    files: int
    bytes: int
    items: list[CleanupItemOut]
    truncated: bool
    errors: list[str]


class BackupOut(BaseModel):
    name: str
    size_bytes: int
    created_at: str | None
    app_version: str | None
    schema_revision: str | None
    counts: dict[str, int | None]
    valid: bool


# --------------------------------------------------------------------------- réglages


def _effective(session: Session, settings: Settings) -> Settings:
    return rs.effective_settings(session, settings)


@router.get("/settings/runtime", response_model=list[RuntimeSettingOut])
def get_runtime_settings(session: SessionDep, settings: SettingsDep) -> list[RuntimeSettingOut]:
    return [RuntimeSettingOut(**d) for d in rs.describe(session, settings)]


@router.put("/settings/runtime", response_model=list[RuntimeSettingOut])
def put_runtime_settings(
    data: RuntimeSettingsIn, session: SessionDep, settings: SettingsDep
) -> list[RuntimeSettingOut]:
    """Appliqué par le worker au début du job suivant (jamais au milieu d'un job)."""
    rs.set_overrides(session, data.values)
    return [RuntimeSettingOut(**d) for d in rs.describe(session, settings)]


# --------------------------------------------------------------------------- stockage


@router.get("/storage", response_model=StorageOut)
def get_storage(session: SessionDep, settings: SettingsDep) -> StorageOut:
    return StorageOut(
        **storage_svc.usage(session, _effective(session, settings)),
        categories=storage_svc.CATEGORIES,
    )


@router.post("/storage/cleanup", response_model=CleanupOut)
def cleanup(data: CleanupIn, session: SessionDep, settings: SettingsDep) -> CleanupOut:
    """``dry_run=true`` (défaut) : aperçu sans rien supprimer. ``false`` : suppression des
    éléments recalculés côté serveur selon les délais de rétention."""
    return CleanupOut(
        **storage_svc.cleanup(
            session, _effective(session, settings), data.categories, dry_run=data.dry_run
        )
    )


# --------------------------------------------------------------------------- sauvegardes


@router.get("/backups", response_model=list[BackupOut])
def list_backups(settings: SettingsDep) -> list[BackupOut]:
    return [BackupOut(**b) for b in backup_svc.list_backups(settings)]


@router.post("/backups", response_model=BackupOut, status_code=status.HTTP_201_CREATED)
def create_backup(session: SessionDep, settings: SettingsDep) -> BackupOut:
    return BackupOut(**backup_svc.create_backup(session, settings))


@router.get("/backups/{name}", response_class=FileResponse)
def download_backup(name: str, settings: SettingsDep) -> FileResponse:
    return FileResponse(
        backup_svc.backup_path(settings, name), media_type="application/zip", filename=name
    )


@router.delete("/backups/{name}", status_code=status.HTTP_204_NO_CONTENT)
def delete_backup(
    name: str,
    settings: SettingsDep,
    confirm: Annotated[bool, Query(description="Doit valoir true")] = False,
) -> Response:
    if not confirm:
        raise AppError("Suppression non confirmée : ajouter ?confirm=true.")
    backup_svc.delete_backup(settings, name)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------------- profils


@router.get("/profiles-export")
def export_profiles(session: SessionDep) -> JSONResponse:
    stamp = datetime.now().strftime("%Y%m%d")
    return JSONResponse(
        backup_svc.export_profiles(session),
        headers={"Content-Disposition": f'attachment; filename="profils-gsa-{stamp}.json"'},
    )


@router.post(
    "/profiles-import", response_model=list[ProfileOut], status_code=status.HTTP_201_CREATED
)
def import_profiles(document: dict[str, Any], session: SessionDep) -> list[ProfileOut]:
    return [profile_out(p) for p in backup_svc.import_profiles(session, document)]
