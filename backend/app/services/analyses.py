"""Analyses de clips : création, lecture, sélection (seuil) et estimation de coût."""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.analysis.candidates import SelectionItem, weighted_score
from app.analysis.candidates import select as select_items
from app.core.config import Settings
from app.core.errors import AppError, NotFoundError
from app.models import CRITERIA, ClipAnalysis, ClipCandidate, Transcript
from app.schemas.analysis import AnalysisOut, CandidateOut, ClipScoreOut, FrameOut
from app.services import profiles as profile_svc
from app.services.queue import enqueue_job
from app.services.sources import get_source, latest_transcript

logger = logging.getLogger(__name__)

# Estimation par extrait (Sonnet 5.5, 8 images 854×480, prompt système en cache) :
# ≈ 7 000 jetons d'entrée + ≈ 1 500 de sortie (réflexion comprise).
EST_INPUT_TOKENS_PER_CLIP = 7000
EST_OUTPUT_TOKENS_PER_CLIP = 1500


def estimate_cost(settings: Settings, n_candidates: int, use_vision: bool) -> float:
    per_input = EST_INPUT_TOKENS_PER_CLIP if use_vision else 3000
    return round(
        n_candidates
        * (
            per_input * settings.llm_price_input_per_mtok
            + EST_OUTPUT_TOKENS_PER_CLIP * settings.llm_price_output_per_mtok
        )
        / 1_000_000,
        3,
    )


def expected_candidates(duration: float, max_candidates: int, min_duration: float) -> int:
    if duration < min_duration:
        return 0
    return max(1, min(max_candidates, int(duration // 45)))


def create_analysis(
    session: Session, project_id: str, profile_id: str | None, engine: str
) -> ClipAnalysis:
    source = get_source(session, project_id)
    if source is None:
        raise AppError("Ce projet n'a pas de source : importez d'abord une vidéo.")
    if latest_transcript(session, source.id) is None or not source.media_path:
        raise AppError(
            "L'import de la vidéo n'est pas terminé (téléchargement et transcription requis)."
        )
    profile = (
        profile_svc.get_profile(session, profile_id)
        if profile_id
        else profile_svc.default_profile(session)
    )
    job = enqueue_job(session, project_id, "analyze_clips", internal=True)
    analysis = ClipAnalysis(
        project_id=project_id,
        job_id=job.id,
        profile_id=profile.id,
        profile_snapshot_json=json.dumps(profile_svc.snapshot(profile), ensure_ascii=False),
        threshold=profile.threshold,
        engine=engine,  # demandé (auto | llm | signals), résolu pendant l'évaluation
        use_vision=profile.use_vision,
    )
    session.add(analysis)
    session.commit()
    logger.info("Analyse créée", extra={"project_id": project_id, "job_id": job.id})
    return analysis


def get_analysis(session: Session, analysis_id: str) -> ClipAnalysis:
    analysis = session.scalar(
        select(ClipAnalysis)
        .where(ClipAnalysis.id == analysis_id)
        .options(selectinload(ClipAnalysis.candidates).selectinload(ClipCandidate.scores))
    )
    if analysis is None:
        raise NotFoundError(f"Analyse introuvable : {analysis_id}")
    return analysis


def list_analyses(session: Session, project_id: str) -> list[ClipAnalysis]:
    return list(
        session.scalars(
            select(ClipAnalysis)
            .where(ClipAnalysis.project_id == project_id)
            .options(selectinload(ClipAnalysis.candidates))
            .order_by(ClipAnalysis.created_at.desc())
        )
    )


def _loads(value: str | None, default: Any) -> Any:
    return json.loads(value) if value else default


def candidate_to_out(c: ClipCandidate) -> CandidateOut:
    frames = _loads(c.frames_json, [])
    return CandidateOut(
        id=c.id,
        position=c.position,
        start_seconds=c.start_seconds,
        end_seconds=c.end_seconds,
        duration_seconds=round(c.end_seconds - c.start_seconds, 2),
        peak_seconds=c.peak_seconds,
        signal_score=c.signal_score,
        status=c.status,
        summary=c.summary,
        reason=c.reason,
        events=_loads(c.events_json, []),
        warnings=_loads(c.warnings_json, []),
        confidence=c.confidence,
        overall_score=c.overall_score,
        selected=c.selected,
        rejection_reason=c.rejection_reason,
        error_message=c.error_message,
        transcript_excerpt=c.transcript_excerpt,
        scores=[
            ClipScoreOut(
                criterion=s.criterion,
                label=CRITERIA.get(s.criterion, s.criterion),
                score=s.score,
                justification=s.justification,
            )
            for s in sorted(c.scores, key=lambda s: list(CRITERIA).index(s.criterion))
        ],
        frames=[
            FrameOut(t=f["t"], url=f"/api/candidates/{c.id}/frames/{i}")
            for i, f in enumerate(frames)
        ],
        signals=_loads(c.signals_json, {}),
    )


def analysis_to_out(analysis: ClipAnalysis, *, with_candidates: bool) -> AnalysisOut:
    snapshot = json.loads(analysis.profile_snapshot_json)
    return AnalysisOut(
        id=analysis.id,
        project_id=analysis.project_id,
        job_id=analysis.job_id,
        profile_id=analysis.profile_id,
        profile_name=snapshot.get("name", "?"),
        threshold=analysis.threshold,
        engine=analysis.engine,
        llm_model=analysis.llm_model,
        use_vision=analysis.use_vision,
        notes=_loads(analysis.notes_json, []),
        cost_usd=round(analysis.cost_usd, 4),
        created_at=analysis.created_at,
        candidate_count=len(analysis.candidates),
        selected_count=sum(1 for c in analysis.candidates if c.selected),
        candidates=[candidate_to_out(c) for c in analysis.candidates] if with_candidates else [],
    )


def apply_selection(
    session: Session, analysis: ClipAnalysis, threshold: float | None = None
) -> int:
    """Recalcule les notes globales et la sélection (sans nouvel appel à l'IA)."""
    if threshold is not None:
        analysis.threshold = threshold
    snapshot = json.loads(analysis.profile_snapshot_json)
    weights = snapshot["weights"]
    min_confidence = float(snapshot.get("min_confidence", 0.0))
    items: list[SelectionItem] = []
    for c in analysis.candidates:
        scored = c.status in {"scored", "signals_only"} and c.scores
        c.overall_score = (
            weighted_score({s.criterion: s.score for s in c.scores}, weights) if scored else None
        )
        items.append(
            SelectionItem(
                c.id,
                c.start_seconds,
                c.end_seconds,
                c.overall_score,
                bool(scored),
                c.confidence if c.status == "scored" else None,
            )
        )
    decisions = select_items(items, analysis.threshold, min_confidence=min_confidence)
    for c in analysis.candidates:
        c.selected, c.rejection_reason = decisions[c.id]
    session.commit()
    return sum(1 for c in analysis.candidates if c.selected)


def frame_path(session: Session, settings: Settings, candidate_id: str, index: int):  # type: ignore[no-untyped-def]
    candidate = session.get(ClipCandidate, candidate_id)
    if candidate is None:
        raise NotFoundError("Extrait introuvable.")
    frames = _loads(candidate.frames_json, [])
    if not 0 <= index < len(frames):
        raise NotFoundError("Image introuvable.")
    path = settings.resolve_data_path(frames[index]["path"])
    if not path.is_file():
        raise NotFoundError("Fichier image absent.")
    return path


def transcript_for(session: Session, project_id: str) -> Transcript | None:
    source = get_source(session, project_id)
    return latest_transcript(session, source.id) if source else None
