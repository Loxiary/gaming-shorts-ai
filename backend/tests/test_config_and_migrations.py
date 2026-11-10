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
    assert current == head == "0001"

    tables = set(inspect(engine).get_table_names())
    assert {"projects", "jobs", "job_steps", "worker_heartbeats", "alembic_version"} <= tables
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
