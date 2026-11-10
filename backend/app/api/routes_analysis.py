from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_session, get_settings_dep
from app.core.config import Settings
from app.models import CRITERIA, ApiUsage
from app.schemas.analysis import (
    AnalysisOut,
    AnalyzeRequest,
    ApiSettingsIn,
    ApiSettingsOut,
    ApiUsageOut,
    CostSummaryOut,
    CriterionOut,
    ProfileIn,
    ProfileOut,
    ReselectRequest,
)
from app.services import analyses as svc
from app.services import budget
from app.services import profiles as profiles_svc
from app.services.projects import get_project
from app.services.sources import get_source

router = APIRouter(prefix="/api", tags=["analysis"])
SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings_dep)]


# --------------------------------------------------------------------------- profils


@router.get("/criteria", response_model=list[CriterionOut])
def list_criteria() -> list[CriterionOut]:
    return [CriterionOut(key=k, label=v) for k, v in CRITERIA.items()]


@router.get("/profiles", response_model=list[ProfileOut])
def list_profiles(session: SessionDep) -> list[ProfileOut]:
    profiles_svc.ensure_default_profiles(session)
    return [profiles_svc.to_out(p) for p in profiles_svc.list_profiles(session)]


@router.post("/profiles", response_model=ProfileOut, status_code=status.HTTP_201_CREATED)
def create_profile(data: ProfileIn, session: SessionDep) -> ProfileOut:
    return profiles_svc.to_out(profiles_svc.create_profile(session, data))


@router.get("/profiles/{profile_id}", response_model=ProfileOut)
def get_profile(profile_id: str, session: SessionDep) -> ProfileOut:
    return profiles_svc.to_out(profiles_svc.get_profile(session, profile_id))


@router.put("/profiles/{profile_id}", response_model=ProfileOut)
def update_profile(profile_id: str, data: ProfileIn, session: SessionDep) -> ProfileOut:
    return profiles_svc.to_out(profiles_svc.update_profile(session, profile_id, data))


@router.post(
    "/profiles/{profile_id}/duplicate",
    response_model=ProfileOut,
    status_code=status.HTTP_201_CREATED,
)
def duplicate_profile(profile_id: str, session: SessionDep) -> ProfileOut:
    return profiles_svc.to_out(profiles_svc.duplicate_profile(session, profile_id))


@router.delete("/profiles/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_profile(profile_id: str, session: SessionDep) -> Response:
    profiles_svc.delete_profile(session, profile_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------------- analyses


@router.get("/projects/{project_id}/analysis-estimate")
def analysis_estimate(
    project_id: str,
    session: SessionDep,
    settings: SettingsDep,
    profile_id: Annotated[str | None, Query(max_length=32)] = None,
) -> dict[str, object]:
    """Estimation du coût IA avant lancement (aucun appel payant)."""
    get_project(session, project_id)
    profiles_svc.ensure_default_profiles(session)
    profile = (
        profiles_svc.get_profile(session, profile_id)
        if profile_id
        else profiles_svc.default_profile(session)
    )
    source = get_source(session, project_id)
    duration = (source.duration_seconds or 0.0) if source else 0.0
    n = svc.expected_candidates(duration, profile.max_candidates, profile.min_duration)
    return {
        "expected_candidates": n,
        "estimated_cost_usd": svc.estimate_cost(settings, n, profile.use_vision),
        "key_configured": settings.anthropic_api_key is not None,
        "api_enabled": budget.api_enabled(session),
        "month_spent_usd": round(budget.month_spent(session), 4),
        "monthly_cap_usd": budget.monthly_cap(session, settings),
        "model": settings.llm_model,
    }


@router.post(
    "/projects/{project_id}/analyses",
    response_model=AnalysisOut,
    status_code=status.HTTP_201_CREATED,
)
def create_analysis(project_id: str, data: AnalyzeRequest, session: SessionDep) -> AnalysisOut:
    get_project(session, project_id)
    profiles_svc.ensure_default_profiles(session)
    analysis = svc.create_analysis(session, project_id, data.profile_id, data.engine)
    return svc.analysis_to_out(svc.get_analysis(session, analysis.id), with_candidates=False)


@router.get("/projects/{project_id}/analyses", response_model=list[AnalysisOut])
def list_analyses(project_id: str, session: SessionDep) -> list[AnalysisOut]:
    get_project(session, project_id)
    return [
        svc.analysis_to_out(a, with_candidates=False)
        for a in svc.list_analyses(session, project_id)
    ]


@router.get("/analyses/{analysis_id}", response_model=AnalysisOut)
def get_analysis(analysis_id: str, session: SessionDep) -> AnalysisOut:
    return svc.analysis_to_out(svc.get_analysis(session, analysis_id), with_candidates=True)


@router.post("/analyses/{analysis_id}/reselect", response_model=AnalysisOut)
def reselect(analysis_id: str, data: ReselectRequest, session: SessionDep) -> AnalysisOut:
    """Change le seuil et recalcule la sélection, sans nouvel appel à l'IA."""
    analysis = svc.get_analysis(session, analysis_id)
    svc.apply_selection(session, analysis, data.threshold)
    return svc.analysis_to_out(svc.get_analysis(session, analysis_id), with_candidates=True)


@router.get("/candidates/{candidate_id}/frames/{index}", response_class=FileResponse)
def candidate_frame(
    candidate_id: str, index: int, session: SessionDep, settings: SettingsDep
) -> FileResponse:
    return FileResponse(
        svc.frame_path(session, settings, candidate_id, index), media_type="image/jpeg"
    )


# --------------------------------------------------------------------------- API et coûts


def _api_settings(session: Session, settings: Settings) -> ApiSettingsOut:
    return ApiSettingsOut(
        provider="anthropic",
        model=settings.llm_model,
        effort=settings.llm_effort,
        key_configured=settings.anthropic_api_key is not None,
        api_enabled=budget.api_enabled(session),
        monthly_cap_usd=budget.monthly_cap(session, settings),
        month_spent_usd=round(budget.month_spent(session), 4),
        prices_per_mtok={
            "input": settings.llm_price_input_per_mtok,
            "output": settings.llm_price_output_per_mtok,
            "cache_read": settings.llm_price_cache_read_per_mtok,
            "cache_write": settings.llm_price_cache_write_per_mtok,
        },
    )


@router.get("/settings/api", response_model=ApiSettingsOut)
def get_api_settings(session: SessionDep, settings: SettingsDep) -> ApiSettingsOut:
    return _api_settings(session, settings)


@router.patch("/settings/api", response_model=ApiSettingsOut)
def update_api_settings(
    data: ApiSettingsIn, session: SessionDep, settings: SettingsDep
) -> ApiSettingsOut:
    if data.api_enabled is not None:
        budget.set_setting(session, budget.API_ENABLED, data.api_enabled)
    if data.monthly_cap_usd is not None:
        budget.set_setting(session, budget.MONTHLY_CAP, round(data.monthly_cap_usd, 2))
    return _api_settings(session, settings)


@router.get("/costs", response_model=CostSummaryOut)
def costs(session: SessionDep, settings: SettingsDep) -> CostSummaryOut:
    month_key = func.strftime("%Y-%m", ApiUsage.created_at)
    by_month = [
        {"month": m, "cost_usd": round(c or 0, 4), "calls": n}
        for m, c, n in session.execute(
            select(month_key, func.sum(ApiUsage.cost_usd), func.count())
            .group_by(month_key)
            .order_by(month_key.desc())
        )
    ]
    recent = list(session.scalars(select(ApiUsage).order_by(ApiUsage.created_at.desc()).limit(100)))
    calls_month = session.scalar(
        select(func.count())
        .select_from(ApiUsage)
        .where(ApiUsage.created_at >= budget.month_start())
    )
    total = session.scalar(select(func.coalesce(func.sum(ApiUsage.cost_usd), 0.0)))
    return CostSummaryOut(
        month_spent_usd=round(budget.month_spent(session), 4),
        monthly_cap_usd=budget.monthly_cap(session, settings),
        total_spent_usd=round(float(total or 0), 4),
        calls_this_month=calls_month or 0,
        by_month=by_month,
        recent=[ApiUsageOut.model_validate(r) for r in recent],
    )
