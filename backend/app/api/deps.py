from __future__ import annotations

from collections.abc import Iterator

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.session import ensure_database_ready


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def get_session(request: Request) -> Iterator[Session]:
    state = request.app.state
    if not state.db_ready:
        # Revérifie à chaque appel tant que la base n'est pas migrée (ex. migration lancée après).
        ensure_database_ready(state.engine, state.settings)  # lève DatabaseNotReadyError (503)
        state.db_ready = True
    session: Session = state.session_factory()
    try:
        yield session
    finally:
        session.close()
