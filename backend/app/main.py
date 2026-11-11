"""Application FastAPI locale. Lancement : ``python -m app.server`` (écoute sur 127.0.0.1)."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import (
    routes_analysis,
    routes_jobs,
    routes_music,
    routes_projects,
    routes_render,
    routes_system,
)
from app.core.config import APP_NAME, APP_VERSION, Settings, get_settings
from app.core.errors import AppError, DatabaseNotReadyError
from app.core.logging import configure_logging
from app.db.session import create_db_engine, create_session_factory, ensure_database_ready
from app.services.profiles import ensure_default_profiles

logger = logging.getLogger("app.api")


def create_app(settings: Settings | None = None, *, configure_logs: bool = True) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if configure_logs:
            configure_logging(settings, "api")
        engine = create_db_engine(settings)
        app.state.settings = settings
        app.state.engine = engine
        app.state.session_factory = create_session_factory(engine)
        try:
            ensure_database_ready(engine, settings)
            app.state.db_ready = True
            with app.state.session_factory() as session:
                ensure_default_profiles(session)
        except DatabaseNotReadyError as exc:
            app.state.db_ready = False
            logger.error(exc.message)
        logger.info("API démarrée — données : %s", settings.data_dir)
        yield
        engine.dispose()

    app = FastAPI(title=APP_NAME, version=APP_VERSION, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type"],
    )

    @app.exception_handler(AppError)
    async def _app_error(_request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Erreur interne sur %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal_error",
                    "message": "Erreur interne du serveur (détails dans data/logs/api.log).",
                }
            },
        )

    app.include_router(routes_system.router)
    app.include_router(routes_projects.router)
    app.include_router(routes_jobs.router)
    app.include_router(routes_analysis.router)
    app.include_router(routes_render.router)
    app.include_router(routes_music.router)
    return app
