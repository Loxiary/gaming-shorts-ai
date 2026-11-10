"""Moteur SQLite, sessions et vérification de l'état des migrations."""

from __future__ import annotations

from typing import Any

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import BACKEND_DIR, Settings
from app.core.errors import DatabaseNotReadyError


def _sqlite_pragmas(dbapi_connection: Any, _record: Any) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")  # intégrité référentielle
    cursor.execute("PRAGMA journal_mode=WAL")  # lectures API concurrentes au worker
    cursor.execute("PRAGMA busy_timeout=5000")  # attente plutôt qu'échec si verrou
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


def create_db_engine(settings: Settings) -> Engine:
    settings.ensure_data_dirs()
    engine = create_engine(
        settings.database_url,
        connect_args={"check_same_thread": False, "timeout": 5},
    )
    event.listen(engine, "connect", _sqlite_pragmas)
    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def alembic_config(settings: Settings) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", settings.database_url)
    return cfg


def upgrade_database(settings: Settings) -> None:
    """Applique les migrations Alembic jusqu'à ``head`` (idempotent)."""
    from alembic import command

    settings.ensure_data_dirs()
    command.upgrade(alembic_config(settings), "head")


def database_revision_status(engine: Engine, settings: Settings) -> tuple[str | None, str | None]:
    """Retourne (révision actuelle, révision attendue)."""
    script = ScriptDirectory.from_config(alembic_config(settings))
    with engine.connect() as conn:
        current = MigrationContext.configure(conn).get_current_revision()
    return current, script.get_current_head()


def ensure_database_ready(engine: Engine, settings: Settings) -> None:
    current, head = database_revision_status(engine, settings)
    if current != head:
        raise DatabaseNotReadyError(
            f"Base de données non migrée (révision {current!r}, attendue {head!r}). "
            "Lancer : python -m app.db.migrate"
        )
