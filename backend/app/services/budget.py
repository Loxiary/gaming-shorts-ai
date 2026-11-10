"""Réglages globaux modifiables (base) et contrôle du budget API.

Le plafond est vérifié AVANT chaque appel payant, à partir d'une estimation haute
(jetons d'entrée comptés + sortie maximale). Aucun appel n'est fait si l'API est
désactivée ou si l'appel pourrait dépasser le plafond du mois en cours.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.time import utcnow
from app.models import ApiUsage, AppSetting

API_ENABLED = "api_enabled"
MONTHLY_CAP = "monthly_cap_usd"


class BudgetExceeded(Exception):
    pass


def get_setting(session: Session, key: str, default: Any) -> Any:
    row = session.get(AppSetting, key)
    return json.loads(row.value_json) if row else default


def set_setting(session: Session, key: str, value: Any) -> None:
    row = session.get(AppSetting, key)
    if row is None:
        session.add(AppSetting(key=key, value_json=json.dumps(value)))
    else:
        row.value_json = json.dumps(value)
    session.commit()


def api_enabled(session: Session) -> bool:
    return bool(get_setting(session, API_ENABLED, True))


def monthly_cap(session: Session, settings: Settings) -> float:
    return float(get_setting(session, MONTHLY_CAP, settings.default_monthly_cap_usd))


def month_start(now: datetime | None = None) -> datetime:
    now = now or utcnow()
    return datetime(now.year, now.month, 1, tzinfo=UTC)


def month_spent(session: Session, now: datetime | None = None) -> float:
    total = session.scalar(
        select(func.coalesce(func.sum(ApiUsage.cost_usd), 0.0)).where(
            ApiUsage.created_at >= month_start(now)
        )
    )
    return float(total or 0.0)


def cost_usd(
    settings: Settings,
    *,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> float:
    return (
        input_tokens * settings.llm_price_input_per_mtok
        + output_tokens * settings.llm_price_output_per_mtok
        + cache_read_tokens * settings.llm_price_cache_read_per_mtok
        + cache_write_tokens * settings.llm_price_cache_write_per_mtok
    ) / 1_000_000


def check_budget(session: Session, settings: Settings, estimated_cost: float) -> None:
    if not api_enabled(session):
        raise BudgetExceeded("L'API est désactivée dans les paramètres.")
    cap = monthly_cap(session, settings)
    spent = month_spent(session)
    if spent + estimated_cost > cap:
        raise BudgetExceeded(
            f"Plafond mensuel atteint : {spent:.2f} $ dépensés + {estimated_cost:.2f} $ "
            f"estimés > {cap:.2f} $. Augmentez le plafond ou attendez le mois prochain."
        )
