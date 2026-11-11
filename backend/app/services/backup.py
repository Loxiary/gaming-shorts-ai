"""Sauvegarde de la base et des paramètres (Phase 6).

Une sauvegarde est une archive ZIP dans ``GSA_DATA_DIR/backups`` contenant :
- ``gaming_shorts.db`` : copie cohérente de la base SQLite (API de sauvegarde SQLite, compatible
  avec le mode WAL, sans arrêter l'application) ;
- ``profiles.json`` : profils de montage (réimportables un par un dans l'interface) ;
- ``settings.json`` : réglages modifiés dans l'interface et configuration NON secrète ;
- ``manifest.json`` : version, révision de schéma, date, contenu.

Jamais inclus : le fichier ``.env``, la clé API, les médias (sources, rendus, exports), les
modèles et la musique (trop volumineux, et réimportables). La restauration se fait hors
ligne, application arrêtée : ``python -m app.cli.backup restore <archive>``.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import zipfile
from pathlib import Path
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import APP_VERSION, Settings
from app.core.errors import AppError, NotFoundError
from app.core.time import utcnow
from app.models import ClipRender, EditingProfile, Project
from app.services import profiles as profile_svc
from app.services import runtime_settings
from app.services.budget import api_enabled, monthly_cap

logger = logging.getLogger(__name__)
NAME_RE = re.compile(r"^gsa-backup-\d{8}-\d{6}(-\d+)?\.zip$")
SECRET_FIELDS = {"anthropic_api_key"}


def backups_dir(settings: Settings) -> Path:
    d = settings.data_dir / "backups"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _public_config(settings: Settings) -> dict[str, Any]:
    data = settings.model_dump(mode="json", exclude=SECRET_FIELDS)
    data["anthropic_api_key_configured"] = settings.anthropic_api_key is not None
    return data


def _sqlite_snapshot(settings: Settings, dest: Path) -> None:
    src = sqlite3.connect(str(settings.db_path))
    try:
        out = sqlite3.connect(str(dest))
        try:
            src.backup(out)
        finally:
            out.close()
    finally:
        src.close()


def create_backup(session: Session, settings: Settings) -> dict[str, Any]:
    now = utcnow()
    folder = backups_dir(settings)
    name = f"gsa-backup-{now:%Y%m%d-%H%M%S}.zip"
    n = 2
    while (folder / name).exists():
        name, n = f"gsa-backup-{now:%Y%m%d-%H%M%S}-{n}.zip", n + 1
    tmp_db = folder / f".{name}.db"
    tmp_zip = folder / f".{name}.part"
    revision = session.scalar(text("SELECT version_num FROM alembic_version"))
    profiles = [
        profile_svc.to_out(p).model_dump(mode="json")
        for p in session.scalars(select(EditingProfile).order_by(EditingProfile.name))
    ]
    manifest = {
        "app_version": APP_VERSION,
        "schema_revision": revision,
        "created_at": now.isoformat(),
        "counts": {
            "projects": session.scalar(select(func.count()).select_from(Project)),
            "profiles": len(profiles),
            "renders": session.scalar(select(func.count()).select_from(ClipRender)),
        },
        "contains": ["gaming_shorts.db", "profiles.json", "settings.json"],
        "not_included": [
            ".env et clé API",
            "vidéos sources, rendus et exports",
            "modèles et bibliothèque musicale",
        ],
    }
    settings_doc = {
        "runtime_overrides": runtime_settings.get_overrides(session),
        "api": {"enabled": api_enabled(session), "monthly_cap_usd": monthly_cap(session, settings)},
        "config": _public_config(settings),
    }
    try:
        _sqlite_snapshot(settings, tmp_db)
        with zipfile.ZipFile(tmp_zip, "w", compression=zipfile.ZIP_DEFLATED) as z:
            z.write(tmp_db, "gaming_shorts.db")
            z.writestr("profiles.json", json.dumps(profiles, ensure_ascii=False, indent=2))
            z.writestr("settings.json", json.dumps(settings_doc, ensure_ascii=False, indent=2))
            z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        tmp_zip.replace(folder / name)
    finally:
        tmp_db.unlink(missing_ok=True)
        tmp_zip.unlink(missing_ok=True)
    logger.info("Sauvegarde créée : %s", name)
    return describe(folder / name)


def describe(path: Path) -> dict[str, Any]:
    manifest: dict[str, Any] = {}
    try:
        with zipfile.ZipFile(path) as z:
            manifest = json.loads(z.read("manifest.json"))
    except (KeyError, zipfile.BadZipFile, json.JSONDecodeError):
        manifest = {}
    return {
        "name": path.name,
        "size_bytes": path.stat().st_size,
        "created_at": manifest.get("created_at"),
        "app_version": manifest.get("app_version"),
        "schema_revision": manifest.get("schema_revision"),
        "counts": manifest.get("counts", {}),
        "valid": bool(manifest),
    }


def list_backups(settings: Settings) -> list[dict[str, Any]]:
    folder = backups_dir(settings)
    files = [p for p in folder.glob("gsa-backup-*.zip") if NAME_RE.match(p.name)]
    return [describe(p) for p in sorted(files, key=lambda p: p.name, reverse=True)]


def backup_path(settings: Settings, name: str) -> Path:
    if not NAME_RE.match(name):
        raise AppError("Nom de sauvegarde invalide.")
    path = backups_dir(settings) / name
    if not path.is_file():
        raise NotFoundError("Sauvegarde introuvable.")
    return path


def delete_backup(settings: Settings, name: str) -> None:
    backup_path(settings, name).unlink()
    logger.info("Sauvegarde supprimée : %s", name)


# --------------------------------------------------------------------------- profils


def export_profiles(session: Session) -> dict[str, Any]:
    return {
        "format": "gaming-shorts-ai/profiles",
        "version": 1,
        "exported_at": utcnow().isoformat(),
        "profiles": [
            profile_svc.to_out(p).model_dump(
                mode="json", exclude={"id", "created_at", "updated_at"}
            )
            for p in session.scalars(select(EditingProfile).order_by(EditingProfile.name))
        ],
    }


def import_profiles(session: Session, document: dict[str, Any]) -> list[EditingProfile]:
    """Ajoute les profils d'un export (jamais de remplacement : un nom pris reçoit un suffixe).
    Chaque profil est validé comme une saisie de l'interface."""
    from pydantic import ValidationError

    from app.schemas.analysis import ProfileIn

    if document.get("format") != "gaming-shorts-ai/profiles":
        raise AppError("Fichier non reconnu : exportez les profils depuis Gaming Shorts AI.")
    items = document.get("profiles")
    if not isinstance(items, list) or not items:
        raise AppError("Le fichier ne contient aucun profil.")
    if len(items) > 100:
        raise AppError("Trop de profils dans le fichier (100 au maximum).")
    parsed: list[ProfileIn] = []
    for i, raw in enumerate(items, start=1):
        try:
            data = ProfileIn.model_validate(raw)
        except ValidationError as exc:
            err = exc.errors()[0]
            where = ".".join(str(x) for x in err.get("loc", ()))
            raise AppError(f"Profil n° {i} invalide ({where}) : {err.get('msg')}") from exc
        data.is_default = False  # l'import ne change jamais le profil par défaut
        parsed.append(data)
    created = []
    for data in parsed:
        base, name, n = data.name, data.name, 2
        while session.scalar(select(EditingProfile.id).where(EditingProfile.name == name)):
            name, n = f"{base} (importé{'' if n == 2 else f' {n - 1}'})"[:120], n + 1
        data.name = name
        created.append(profile_svc.create_profile(session, data))
    logger.info("%d profil(s) importé(s)", len(created))
    return created
