from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.db.session import create_db_engine, create_session_factory, upgrade_database
from app.main import create_app
from app.workers.runner import Worker


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    # Dossier data isolé par test : aucune donnée réelle n'est touchée.
    return Settings(
        _env_file=None,
        data_dir=tmp_path / "data",
        demo_step_seconds=0,
        worker_stale_seconds=30,
    )


@pytest.fixture
def migrated(settings: Settings) -> Settings:
    upgrade_database(settings)
    return settings


@pytest.fixture
def session_factory(migrated: Settings) -> Iterator[sessionmaker[Session]]:
    engine = create_db_engine(migrated)
    yield create_session_factory(engine)
    engine.dispose()


@pytest.fixture
def client(migrated: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(migrated, configure_logs=False)) as c:
        yield c


@pytest.fixture
def worker(migrated: Settings, session_factory: sessionmaker[Session]) -> Worker:
    return Worker(migrated, session_factory)


@pytest.fixture
def project_id(client: TestClient) -> str:
    r = client.post("/api/projects", json={"name": "Projet test", "is_test": True})
    assert r.status_code == 201
    return r.json()["id"]
