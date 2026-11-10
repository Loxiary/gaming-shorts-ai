from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from pydantic import ValidationError
from sqlalchemy import inspect

from app.core.config import DATA_SUBDIRS, Settings
from app.core.errors import DatabaseNotReadyError
from app.db.session import (
    alembic_config,
    create_db_engine,
    database_revision_status,
    ensure_database_ready,
    upgrade_database,
)


def test_data_dirs_created(settings: Settings) -> None:
    settings.ensure_data_dirs()
    for name in DATA_SUBDIRS:
        assert (settings.data_dir / name).is_dir()


def test_relative_data_dir_is_made_absolute() -> None:
    s = Settings(_env_file=None, data_dir=Path("data-relatif"))
    assert s.data_dir.is_absolute()


def test_api_host_must_be_loopback(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, data_dir=tmp_path, api_host="0.0.0.0")
    assert Settings(_env_file=None, data_dir=tmp_path, api_host="127.0.0.1").api_host == "127.0.0.1"


def test_unknown_subdir_rejected(settings: Settings) -> None:
    with pytest.raises(ValueError):
        settings.subdir("../../etc")


def test_migrations_upgrade_to_head(settings: Settings) -> None:
    engine = create_db_engine(settings)
    with pytest.raises(DatabaseNotReadyError):
        ensure_database_ready(engine, settings)

    upgrade_database(settings)
    ensure_database_ready(engine, settings)
    current, head = database_revision_status(engine, settings)
    assert current == head == "0002"

    tables = set(inspect(engine).get_table_names())
    assert {
        "projects",
        "jobs",
        "job_steps",
        "worker_heartbeats",
        "alembic_version",
        "source_media",
        "transcripts",
        "transcript_segments",
    } <= tables
    engine.dispose()


def test_migrations_idempotent_and_reversible(settings: Settings) -> None:
    upgrade_database(settings)
    upgrade_database(settings)  # deuxième passage sans effet
    cfg = alembic_config(settings)
    command.downgrade(cfg, "base")
    engine = create_db_engine(settings)
    assert "projects" not in inspect(engine).get_table_names()
    engine.dispose()
    command.upgrade(cfg, "head")


def test_sqlite_pragmas(migrated: Settings) -> None:
    engine = create_db_engine(migrated)
    with engine.connect() as conn:
        assert conn.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
        assert conn.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"
    engine.dispose()


def test_upgrade_0001_to_0002_keeps_existing_steps(settings: Settings) -> None:
    """La base réelle de Phase 1 contient déjà des étapes : la migration doit les conserver."""
    cfg = alembic_config(settings)
    settings.ensure_data_dirs()
    command.upgrade(cfg, "0001")
    engine = create_db_engine(settings)
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO projects (id, name, is_test, created_at, updated_at) "
            "VALUES ('p1', 'Ancien', 1, '2026-11-10 10:00:00', '2026-11-10 10:00:00')"
        )
        conn.exec_driver_sql(
            "INSERT INTO jobs (id, project_id, kind, status, progress, cancel_requested, attempts,"
            " created_at, updated_at) VALUES ('j1', 'p1', 'demo', 'completed', 1, 0, 1,"
            " '2026-11-10 10:00:00', '2026-11-10 10:00:00')"
        )
        conn.exec_driver_sql(
            "INSERT INTO job_steps (id, job_id, position, name, label, status)"
            " VALUES ('s1', 'j1', 0, 'demo_prepare', 'Préparation', 'completed')"
        )
    command.upgrade(cfg, "head")
    with engine.connect() as conn:
        row = conn.exec_driver_sql("SELECT status, progress, detail FROM job_steps").one()
    assert tuple(row) == ("completed", 0.0, None)
    engine.dispose()
