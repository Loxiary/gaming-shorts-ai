"""Espace disque, rétention et nettoyage (Phase 6).

Règles de sûreté :
- le nettoyage se fait en deux temps : aperçu (rien n'est supprimé), puis exécution confirmée ;
  la liste à supprimer est TOUJOURS recalculée côté serveur (aucun chemin fourni par le client) ;
- seuls des fichiers sous le dossier de données sont touchés ; jamais les exports, les
  modèles, la bibliothèque musicale, les journaux ni la base courante ;
- rien n'est supprimé pour un projet dont un job est en attente, en cours ou en pause ;
- les fiches (projets, transcriptions, analyses, rapports, rendus) sont conservées : seule la
  place disque est libérée, et l'interface indique ce qui doit être régénéré.
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import DATA_SUBDIRS, Settings
from app.core.errors import AppError
from app.core.time import utcnow
from app.models import (
    ACTIVE_JOB_STATUSES,
    TERMINAL_JOB_STATUSES,
    ClipRender,
    Job,
    Project,
    SourceMedia,
)

logger = logging.getLogger(__name__)

CATEGORIES = {
    "temp": "Fichiers intermédiaires (régénérables)",
    "renders": "Shorts jamais exportés",
    "sources": "Vidéos sources",
    "db_backups": "Anciennes sauvegardes de migration de la base",
}
# Fichiers d'un dossier de rendu qui ne servent plus une fois le rendu terminé.
RENDER_INTERMEDIATES = ("audio_mix.wav", "game_attenuated.wav", "subtitles.ass")
RENDER_INTERMEDIATE_DIRS = ("narration", "facecam")


@dataclass
class Item:
    category: str
    path: Path
    bytes: int
    reason: str
    project_id: str | None = None
    render_id: str | None = None


def _size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    if path.is_dir():
        return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    return 0


def _mtime(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)


def _inside(settings: Settings, path: Path) -> bool:
    root = settings.data_dir.resolve()
    try:
        return path.resolve().is_relative_to(root) and path.resolve() != root
    except OSError:
        return False


def _busy_projects(session: Session) -> set[str]:
    return set(session.scalars(select(Job.project_id).where(Job.status.in_(ACTIVE_JOB_STATUSES))))


def _last_activity(session: Session) -> dict[str, datetime]:
    rows = session.execute(
        select(Job.project_id, func.max(func.coalesce(Job.finished_at, Job.updated_at))).group_by(
            Job.project_id
        )
    )
    return {pid: ts for pid, ts in rows if ts is not None}


# --------------------------------------------------------------------------- inventaire


def usage(session: Session, settings: Settings) -> dict[str, Any]:
    disk = shutil.disk_usage(settings.data_dir)
    dirs = {name: _size(settings.subdir(name)) for name in DATA_SUBDIRS}
    db_files = [p for p in settings.data_dir.glob("*.db*") if p.is_file()]
    current_db = sum(p.stat().st_size for p in db_files if p.name.startswith(settings.db_path.name))
    backups = sum(p.stat().st_size for p in db_files) - current_db
    projects = []
    names = dict(session.execute(select(Project.id, Project.name)).all())
    activity = _last_activity(session)
    for pid, name in names.items():
        src = _size(settings.subdir("sources") / pid)
        work = settings.subdir("projects") / pid
        analysis = _size(work / "analysis")
        renders = _size(work / "renders")
        other = _size(work) - analysis - renders
        projects.append(
            {
                "project_id": pid,
                "name": name,
                "source_bytes": src + other,  # vidéo + audio 16 kHz extrait
                "analysis_bytes": analysis,
                "renders_bytes": renders,
                "total_bytes": src + _size(work),
                "last_activity": activity.get(pid),
            }
        )
    projects.sort(key=lambda p: -p["total_bytes"])
    return {
        "data_dir": str(settings.data_dir),
        "disk_total_bytes": disk.total,
        "disk_free_bytes": disk.free,
        "min_free_disk_gb": settings.min_free_disk_gb,
        "directories": dirs,
        "database_bytes": current_db,
        "db_backups_bytes": backups,
        "projects": projects,
        "retention": {
            "temp_days": settings.retention_temp_days,
            "render_days": settings.retention_render_days,
            "source_days": settings.retention_source_days,
            "auto": settings.retention_auto,
        },
    }


# --------------------------------------------------------------------------- candidats


def _older(ts: datetime | None, days: int, now: datetime) -> bool:
    return days > 0 and ts is not None and ts <= now - timedelta(days=days)


def _temp_items(session: Session, settings: Settings, now: datetime) -> list[Item]:
    days = settings.retention_temp_days
    if days <= 0:
        return []
    items: list[Item] = []
    busy = _busy_projects(session)
    temp = settings.subdir("temp")
    for p in sorted(temp.iterdir()) if temp.is_dir() else []:
        if _older(_mtime(p), days, now):
            items.append(Item("temp", p, _size(p), f"dossier temporaire, plus de {days} j"))
    renders = session.execute(
        select(ClipRender.id, ClipRender.project_id, Job.status, Job.finished_at).join(
            Job, Job.id == ClipRender.job_id
        )
    )
    for rid, pid, status, finished in renders:
        if pid in busy or status not in TERMINAL_JOB_STATUSES or not _older(finished, days, now):
            continue
        work = settings.subdir("projects") / pid / "renders" / rid
        for name in RENDER_INTERMEDIATES + RENDER_INTERMEDIATE_DIRS:
            p = work / name
            if p.exists():
                items.append(
                    Item("temp", p, _size(p), "fichier de travail d'un rendu terminé", pid, rid)
                )
    for proxy in settings.subdir("projects").glob("*/analysis/proxy_*.mp4"):
        pid = proxy.parent.parent.name
        if pid not in busy and _older(_mtime(proxy), days, now):
            items.append(
                Item("temp", proxy, _size(proxy), "copie d'analyse (recréée si besoin)", pid)
            )
    return items


def _render_items(session: Session, settings: Settings, now: datetime) -> list[Item]:
    days = settings.retention_render_days
    if days <= 0:
        return []
    busy = _busy_projects(session)
    items: list[Item] = []
    rows = session.scalars(select(ClipRender).where(ClipRender.export_status != "exported"))
    for r in rows:
        if r.project_id in busy or not _older(r.created_at, days, now):
            continue
        work = settings.subdir("projects") / r.project_id / "renders" / r.id
        if work.is_dir() and _size(work) > 0:
            items.append(
                Item(
                    "renders",
                    work,
                    _size(work),
                    f"jamais exporté, créé il y a plus de {days} j",
                    r.project_id,
                    r.id,
                )
            )
    return items


def _source_items(session: Session, settings: Settings, now: datetime) -> list[Item]:
    days = settings.retention_source_days
    if days <= 0:
        return []
    busy = _busy_projects(session)
    activity = _last_activity(session)
    items: list[Item] = []
    for src in session.scalars(select(SourceMedia)):
        pid = src.project_id
        if pid in busy or not _older(activity.get(pid), days, now):
            continue
        for rel in (src.media_path, src.audio_path):
            if not rel:
                continue
            try:
                p = settings.resolve_data_path(rel)
            except ValueError:
                continue
            if p.is_file():
                items.append(
                    Item("sources", p, _size(p), f"projet inactif depuis plus de {days} j", pid)
                )
    return items


def _backup_items(settings: Settings) -> list[Item]:
    """Sauvegardes automatiques faites avant chaque migration : on garde la plus récente."""
    groups: dict[str, list[Path]] = {}
    for p in settings.data_dir.glob(f"{settings.db_path.stem}.backup-*.db*"):
        stem = p.name.split(".db")[0]
        groups.setdefault(stem, []).append(p)
    stems = sorted(groups, key=lambda st: max(_mtime(p) for p in groups[st]))
    items = []
    for stem in stems[:-1]:
        for p in groups[stem]:
            items.append(Item("db_backups", p, _size(p), "sauvegarde de migration ancienne"))
    return items


def candidates(session: Session, settings: Settings, categories: list[str]) -> list[Item]:
    unknown = set(categories) - set(CATEGORIES)
    if unknown:
        raise AppError(f"Catégorie de nettoyage inconnue : {', '.join(sorted(unknown))}")
    now = utcnow()
    items: list[Item] = []
    if "temp" in categories:
        items += _temp_items(session, settings, now)
    if "renders" in categories:
        items += _render_items(session, settings, now)
    if "sources" in categories:
        items += _source_items(session, settings, now)
    if "db_backups" in categories:
        items += _backup_items(settings)
    return [i for i in items if _inside(settings, i.path) and not _protected(settings, i.path)]


def _protected(settings: Settings, path: Path) -> bool:
    resolved = path.resolve()
    for name in ("exports", "models", "music", "logs"):
        if resolved.is_relative_to(settings.subdir(name).resolve()):
            return True
    return resolved.name.startswith(settings.db_path.name)  # base courante (+ -wal / -shm)


# --------------------------------------------------------------------------- exécution


def cleanup(
    session: Session, settings: Settings, categories: list[str], *, dry_run: bool
) -> dict[str, Any]:
    items = candidates(session, settings, categories)
    freed = 0
    deleted = 0
    errors: list[str] = []
    if not dry_run:
        for item in items:
            try:
                if item.path.is_dir():
                    shutil.rmtree(item.path)
                else:
                    item.path.unlink(missing_ok=True)
                freed += item.bytes
                deleted += 1
            except OSError as exc:
                errors.append(f"{settings.to_relative(item.path)} : {exc}")
        _update_records(session, settings, items)
        logger.info(
            "Nettoyage : %d élément(s), %d octets libérés (%s)",
            deleted,
            freed,
            ",".join(categories),
        )
    return {
        "dry_run": dry_run,
        "categories": categories,
        "files": len(items) if dry_run else deleted,
        "bytes": sum(i.bytes for i in items) if dry_run else freed,
        "items": [
            {
                "category": i.category,
                "path": settings.to_relative(i.path),
                "bytes": i.bytes,
                "reason": i.reason,
                "project_id": i.project_id,
            }
            for i in items[:500]
        ],
        "truncated": len(items) > 500,
        "errors": errors,
    }


def _update_records(session: Session, settings: Settings, items: list[Item]) -> None:
    """Les fiches restent ; on efface les chemins des fichiers disparus."""
    projects = {i.project_id for i in items if i.category == "sources" and i.project_id}
    for src in session.scalars(select(SourceMedia).where(SourceMedia.project_id.in_(projects))):
        for attr in ("media_path", "audio_path"):
            rel = getattr(src, attr)
            if rel and not settings.resolve_data_path(rel).is_file():
                setattr(src, attr, None)
    renders = {i.render_id for i in items if i.category == "renders" and i.render_id}
    for r in session.scalars(select(ClipRender).where(ClipRender.id.in_(renders))):
        r.output_path = None
        r.preview_audio_path = None
        r.files_purged = True
    session.commit()
