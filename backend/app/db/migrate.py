"""Point d'entrée : ``python -m app.db.migrate`` applique les migrations jusqu'à head."""

from __future__ import annotations

import logging

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import upgrade_database

logger = logging.getLogger("app.db.migrate")


def main() -> None:
    settings = get_settings()
    configure_logging(settings, "migrate")
    logger.info("Migration de la base %s", settings.db_path)
    upgrade_database(settings)
    logger.info("Base à jour")


if __name__ == "__main__":
    main()
