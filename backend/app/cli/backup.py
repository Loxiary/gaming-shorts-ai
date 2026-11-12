"""Sauvegarde et restauration de la base en ligne de commande.

    python -m app.cli.backup create
    python -m app.cli.backup list
    python -m app.cli.backup restore <archive.zip> [--yes]

La restauration exige que l'application soit ARRÊTÉE (scripts\\stop.ps1) : la base courante
est d'abord copiée à côté (gaming_shorts.avant-restauration-<date>.db), puis remplacée par
celle de l'archive, puis migrée vers le schéma courant si l'archive est plus ancienne.
Les médias ne sont pas dans l'archive : un projet dont la vidéo manque peut la retélécharger.
"""

from __future__ import annotations

import argparse
import shutil
import socket
import sqlite3
import sys
import zipfile
from pathlib import Path

from app.core.config import Settings, get_settings
from app.core.time import utcnow


def _port_open(host: str, port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def _worker_alive(db: Path) -> bool:
    if not db.is_file():
        return False
    con = sqlite3.connect(str(db))
    try:
        row = con.execute(
            "SELECT max(last_seen_at) FROM worker_heartbeats WHERE last_seen_at > "
            "strftime('%Y-%m-%d %H:%M:%f', 'now', '-60 seconds')"
        ).fetchone()
        return bool(row and row[0])
    except sqlite3.Error:
        return False
    finally:
        con.close()


def restore(archive: Path, yes: bool, settings: Settings | None = None) -> int:
    settings = settings or get_settings()
    if _port_open(settings.api_host, settings.api_port) or _worker_alive(settings.db_path):
        print("L'application semble lancée : arrêtez-la d'abord (scripts\\stop.ps1).")
        return 2
    try:
        with zipfile.ZipFile(archive) as z:
            names = set(z.namelist())
            if "gaming_shorts.db" not in names or "manifest.json" not in names:
                print("Archive invalide : ce n'est pas une sauvegarde Gaming Shorts AI.")
                return 2
            manifest = z.read("manifest.json").decode("utf-8")
            print("Sauvegarde :", manifest)
            if not yes:
                answer = input(
                    "La base actuelle sera remplacée (une copie de sécurité est faite). "
                    "Continuer ? [o/N] "
                )
                if answer.strip().lower() not in {"o", "oui", "y"}:
                    print("Annulé.")
                    return 1
            stamp = f"{utcnow():%Y%m%d-%H%M%S}"
            db = settings.db_path
            if db.exists():
                safety = db.with_name(f"{db.stem}.avant-restauration-{stamp}.db")
                src = sqlite3.connect(str(db))
                out = sqlite3.connect(str(safety))
                src.backup(out)
                out.close()
                src.close()
                print(f"Copie de sécurité : {safety}")
            tmp = db.with_name(f"{db.stem}.restauration-{stamp}.tmp")
            with z.open("gaming_shorts.db") as fsrc, tmp.open("wb") as fdst:
                shutil.copyfileobj(fsrc, fdst)
    except zipfile.BadZipFile:
        print("Archive illisible.")
        return 2
    check = sqlite3.connect(str(tmp))
    ok = check.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    check.close()
    if not ok:
        tmp.unlink()
        print("La base de l'archive est corrompue : restauration abandonnée.")
        return 2
    try:
        for suffix in ("-wal", "-shm"):
            Path(str(db) + suffix).unlink(missing_ok=True)
        tmp.replace(db)
    except PermissionError:
        tmp.unlink(missing_ok=True)
        print("La base est encore ouverte par un programme : arrêtez l'application et réessayez.")
        return 2
    from app.db.session import upgrade_database

    upgrade_database(settings)  # archive plus ancienne : schéma mis à jour
    print("Restauration terminée. Relancez l'application (scripts\\start.ps1).")
    return 0


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    parser = argparse.ArgumentParser(prog="python -m app.cli.backup")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("create", help="Crée une sauvegarde (base + paramètres)")
    sub.add_parser("list", help="Liste les sauvegardes")
    r = sub.add_parser("restore", help="Restaure une sauvegarde (application arrêtée)")
    r.add_argument("archive", type=Path)
    r.add_argument("--yes", action="store_true", help="Ne pas demander de confirmation")
    args = parser.parse_args()
    settings = get_settings()
    from app.services import backup

    if args.cmd == "restore":
        return restore(args.archive, args.yes)
    if args.cmd == "list":
        for b in backup.list_backups(settings):
            print(f"{b['name']}  {b['size_bytes'] / 1e6:.1f} Mo  schéma {b['schema_revision']}")
        return 0
    from app.db.session import create_db_engine, create_session_factory

    engine = create_db_engine(settings)
    with create_session_factory(engine)() as s:
        b = backup.create_backup(s, settings)
    engine.dispose()
    print(f"Sauvegarde créée : {backups_path(settings) / b['name']}")
    return 0


def backups_path(settings):  # type: ignore[no-untyped-def]
    from app.services.backup import backups_dir

    return backups_dir(settings)


if __name__ == "__main__":
    raise SystemExit(main())
