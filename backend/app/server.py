"""Point d'entrée : ``python -m app.server`` — lance l'API sur l'hôte/port configurés."""

from __future__ import annotations

import uvicorn

from app.core.config import get_settings
from app.main import create_app


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        create_app(settings),
        host=settings.api_host,
        port=settings.api_port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
