"""Étapes du job ``render_clip`` (Phase 4) : plan éditorial, sous-titres, rendu, QC, risques.

Le rendu n'est jamais exporté automatiquement : l'export exige une confirmation explicite
de l'utilisateur (API /renders/{id}/confirm-export) après lecture des avertissements.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.llm import LLMResult, StructuredLLM
from app.models import (
    ApiUsage,
    ClipRender,
    SourceMedia,
    Transcript,
    TranscriptSegment,
)
from app.render import editorial as ed
from app.render.ffmpeg_render import quality_check, render_short
from app.render.risk import build_risk_report
from app.render.style import normalize_subtitle_style
from app.render.subtitles import build_ass, cues_from_translation, cues_from_words
from app.services import budget
from app.workers.context import StepContext
from app.workers.errors import StepError


def _render(ctx: StepContext, s: Session) -> ClipRender:
    r = s.scalar(select(ClipRender).where(ClipRender.job_id == ctx.job_id))
    if r is None:
        raise StepError("Rendu introuvable pour ce job.")
    return r


def _source(ctx: StepContext, s: Session) -> SourceMedia:
    src = s.scalar(select(SourceMedia).where(SourceMedia.project_id == ctx.project_id))
    if src is None or not src.media_path:
        raise StepError("Vidéo source absente : relancez l'import.")
    return src


def _workdir(ctx: StepContext, render_id: str) -> Path:
    d = ctx.settings.subdir("projects") / ctx.project_id / "renders" / render_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _sentences(
    s: Session, source_id: str, start: float, end: float
) -> tuple[list[ed.Sentence], str | None]:
    """Phrases de l'extrait, temps relatifs au début du short (mots horodatés)."""
    t = s.scalar(
        select(Transcript)
        .where(Transcript.source_media_id == source_id, Transcript.kind == "source")
        .order_by(Transcript.created_at.desc())
        .limit(1)
    )
    if t is None:
        raise StepError("Transcription absente : relancez l'import.")
    segs = s.scalars(
        select(TranscriptSegment)
        .where(TranscriptSegment.transcript_id == t.id)
        .order_by(TranscriptSegment.position)
    )
    sentences: list[ed.Sentence] = []
    current: list[tuple[float, float, str]] = []
    for seg in segs:
        words = json.loads(seg.words_json) if seg.words_json else []
        if not words:
            words = [{"start": seg.start_seconds, "end": seg.end_seconds, "word": seg.text}]
        for w in words:
            a, b = float(w["start"]), float(w["end"])
            if (a + b) / 2 < start or (a + b) / 2 >= end:
                continue
            current.append(
                (max(a - start, 0.0), min(b - start, end - start), str(w["word"]).strip())
            )
            if str(w["word"]).strip().endswith((".", "!", "?", "…")):
                sentences.append(_sentence(current))
                current = []
    if current:
        sentences.append(_sentence(current))
    return sentences, t.language


def _sentence(words: list[tuple[float, float, str]]) -> ed.Sentence:
    return ed.Sentence(words[0][0], words[-1][1], " ".join(w for _, _, w in words), list(words))


def _recorder(ctx: StepContext, purpose: str):  # type: ignore[no-untyped-def]
    def record(result: LLMResult[Any]) -> None:
        u = result.usage
        cost = budget.cost_usd(
            ctx.settings,
            input_tokens=u.input_tokens,
            output_tokens=u.output_tokens,
            cache_read_tokens=u.cache_read_tokens,
            cache_write_tokens=u.cache_write_tokens,
        )
        with ctx.session_factory() as s:
            s.add(
                ApiUsage(
                    provider="anthropic",
                    model=result.model,
                    purpose=purpose,
                    project_id=ctx.project_id,
                    job_id=ctx.job_id,
                    input_tokens=u.input_tokens,
                    output_tokens=u.output_tokens,
                    cache_read_tokens=u.cache_read_tokens,
                    cache_write_tokens=u.cache_write_tokens,
                    images=0,
                    cost_usd=round(cost, 6),
                    status=result.status,
                    request_id=result.request_id,
                    detail=result.error,
                )
            )
            r = _render(ctx, s)
            r.cost_usd = (r.cost_usd or 0) + cost
            s.commit()
        ctx.heartbeat()

    return record


def _budget(ctx: StepContext):  # type: ignore[no-untyped-def]
    def check(estimate: float) -> None:
        with ctx.session_factory() as s:
            budget.check_budget(s, ctx.settings, estimate)

    return check


def _llm(ctx: StepContext) -> StructuredLLM | None:
    llm = getattr(ctx.adapters, "editor", None)
    if llm is None:
        return None
    with ctx.session_factory() as s:
        enabled = budget.api_enabled(s)
    return llm if (getattr(llm, "configured", False) and enabled) else None


# --------------------------------------------------------------------------- 1. plan


def creating_editorial_plan(ctx: StepContext) -> dict[str, Any]:
    with ctx.session_factory() as s:
        r = _render(ctx, s)
        profile = json.loads(r.profile_snapshot_json)
        cand = json.loads(r.candidate_snapshot_json) if r.candidate_snapshot_json else {}
        source = _source(ctx, s)
        sentences, _ = _sentences(s, source.id, r.start_seconds, r.end_seconds)
        duration = r.end_seconds - r.start_seconds
        offset = r.start_seconds
    hook_enabled = bool(profile.get("hook_enabled", True))
    cta_enabled = bool(profile.get("cta_enabled", True))
    language = profile.get("output_language", "fr")

    plan: ed.EditorialPlan | None = None
    engine = "fallback"
    note: str | None = None
    llm = _llm(ctx)
    if llm is not None:
        try:
            result = llm.call(
                system=ed.editorial_system(
                    language,
                    profile.get("editorial_focus"),
                    profile.get("name", ""),
                    profile.get("cta_text"),
                ),
                content=ed.editorial_content(
                    cand.get("summary"),
                    cand.get("reason"),
                    cand.get("events", []),
                    sentences,
                    duration,
                    offset,
                ),
                schema=ed.EditorialPlan,
                budget_check=_budget(ctx),
                record=_recorder(ctx, "editorial_plan"),
                validate=lambda p: ed.validate_plan(p, sentences, duration, hook_enabled) and None,
                max_tokens=6000,
            )
            if result.status == "ok" and result.parsed is not None:
                plan, engine = result.parsed, "llm"
            else:
                note = f"Plan IA indisponible ({result.error}) : plan de repli utilisé."
        except budget.BudgetExceeded as exc:
            note = f"{exc} Plan de repli utilisé (sans IA)."
    else:
        note = "IA indisponible (clé absente ou API désactivée) : plan de repli utilisé."

    if plan is None:
        peaks = [float(p) - offset for p in cand.get("signals", {}).get("audio_peaks", [])]
        plan = ed.fallback_plan(
            sentences,
            [p for p in peaks if 0 <= p <= duration],
            duration,
            hook_enabled,
            profile.get("cta_text"),
            language,
        )
    if not hook_enabled:
        plan.hook_text = ""
    if not cta_enabled:
        plan.cta_text = ""
    if note:
        plan.warnings.append(note)

    with ctx.session_factory() as s:
        r = _render(ctx, s)
        r.plan_json = plan.model_dump_json()
        r.plan_engine = engine
        s.commit()
    return {
        "engine": engine,
        "hook": plan.hook_text,
        "cta": plan.cta_text,
        "zooms": len(plan.zooms),
        "keywords": len(plan.keywords),
    }


# --------------------------------------------------------------------------- 2. sous-titres


def preparing_subtitles(ctx: StepContext) -> dict[str, Any]:
    with ctx.session_factory() as s:
        r = _render(ctx, s)
        profile = json.loads(r.profile_snapshot_json)
        plan = ed.EditorialPlan.model_validate_json(r.plan_json or "{}")
        source = _source(ctx, s)
        sentences, src_lang = _sentences(s, source.id, r.start_seconds, r.end_seconds)
        duration = r.end_seconds - r.start_seconds
        render_id = r.id
    mode = profile.get("subtitle_mode", "source")
    style = normalize_subtitle_style(profile.get("subtitle_style"))
    target = profile.get("output_language", "fr")
    translated = False
    language = src_lang
    notes: list[str] = []

    cues = []
    if mode != "off":
        words = [w for s_ in sentences for w in s_.words]
        cues = cues_from_words(words, style["max_words"], duration)
        if mode == "translate" and src_lang and src_lang != target and sentences:
            llm = _llm(ctx)
            if llm is None:
                notes.append(
                    "Traduction impossible sans IA : sous-titres dans la langue d'origine."
                )
            else:
                try:
                    result = llm.call(
                        system=ed.translation_system(src_lang, target),
                        content=ed.translation_content(sentences),
                        schema=ed.Translation,
                        budget_check=_budget(ctx),
                        record=_recorder(ctx, "subtitle_translation"),
                        validate=lambda tr: ed.validate_translation(tr, len(sentences)),
                        max_tokens=8000,
                    )
                    if result.status == "ok" and result.parsed is not None:
                        texts = [
                            x.text for x in sorted(result.parsed.sentences, key=lambda x: x.index)
                        ]
                        cues = cues_from_translation(sentences, texts, style["max_words"], duration)
                        translated, language = True, target
                    else:
                        notes.append(f"Traduction échouée ({result.error}) : langue d'origine.")
                except budget.BudgetExceeded as exc:
                    notes.append(f"{exc} Sous-titres dans la langue d'origine.")

    keywords = ed.filter_keywords(plan.keywords, [w for c in cues for (_, _, w) in c.words])
    ass = build_ass(
        cues=cues,
        style=style,
        keywords=keywords,
        hook=plan.hook_text or None,
        cta=plan.cta_text or None,
        duration=duration,
        layout=profile.get("layout", "blur"),
    )
    (_workdir(ctx, render_id) / "subtitles.ass").write_text(ass, encoding="utf-8")

    with ctx.session_factory() as s:
        r = _render(ctx, s)
        plan.keywords = keywords
        plan.warnings += notes
        r.plan_json = plan.model_dump_json()
        r.subtitles_json = json.dumps([c.to_json() for c in cues], ensure_ascii=False)
        r.subtitle_language = language if mode != "off" else None
        r.subtitles_are_translation = translated
        s.commit()
    return {
        "mode": mode,
        "cues": len(cues),
        "language": language,
        "translated": translated,
        "keywords": keywords,
    }


# --------------------------------------------------------------------------- 3. rendu


def rendering(ctx: StepContext) -> dict[str, Any]:
    with ctx.session_factory() as s:
        r = _render(ctx, s)
        profile = json.loads(r.profile_snapshot_json)
        plan = ed.EditorialPlan.model_validate_json(r.plan_json or "{}")
        source = _source(ctx, s)
        src_path = ctx.settings.resolve_data_path(source.media_path or "")
        info = (source.video_codec, source.width or 1920, source.height or 1080, source.fps)
        start, duration, render_id = r.start_seconds, r.end_seconds - r.start_seconds, r.id
    workdir = _workdir(ctx, render_id)
    if not (workdir / "subtitles.ass").is_file():
        raise StepError("Fichier de sous-titres absent : relancez le montage.")
    out = render_short(
        source=src_path,
        workdir=workdir,
        ass_name="subtitles.ass",
        out_name="short",
        start=start,
        duration=duration,
        layout=profile.get("layout", "blur"),
        encoder=profile.get("render_encoder", "libx264"),
        src_codec=info[0],
        src_w=info[1],
        src_h=info[2],
        src_fps=info[3],
        zooms=plan.zooms,
        zoom_intensity=float(profile.get("zoom_intensity", 0.12)),
        on_progress=ctx.report_progress,
        check_cancel=ctx.check_cancel,
        x264_preset=ctx.settings.render_x264_preset,
    )
    with ctx.session_factory() as s:
        r = _render(ctx, s)
        r.output_path = ctx.settings.to_relative(out)
        r.output_size_bytes = out.stat().st_size
        s.commit()
    return {"output_path": ctx.settings.to_relative(out), "size_bytes": out.stat().st_size}


# --------------------------------------------------------------------------- 4. QC


def quality_checking(ctx: StepContext) -> dict[str, Any]:
    with ctx.session_factory() as s:
        r = _render(ctx, s)
        out = ctx.settings.resolve_data_path(r.output_path or "")
        expected = r.end_seconds - r.start_seconds
    ctx.report_progress(0.2, "Analyse du fichier produit…")
    qc = quality_check(out, expected)
    with ctx.session_factory() as s:
        r = _render(ctx, s)
        r.qc_json = json.dumps(qc, ensure_ascii=False)
        r.qc_passed = qc["passed"]
        s.commit()
    failed = [c["label"] for c in qc["checks"] if not c["ok"] and c["level"] == "critical"]
    if failed:
        # Fichier invalide : il n'est jamais marqué prêt ; les diagnostics restent consultables.
        raise StepError("Contrôle qualité échoué : " + " ; ".join(failed))
    return {
        "passed": qc["passed"],
        "warnings": sum(1 for c in qc["checks"] if not c["ok"]),
        **qc["measures"],
    }


# --------------------------------------------------------------------------- 5. risques


def building_risk_report(ctx: StepContext) -> dict[str, Any]:
    with ctx.session_factory() as s:
        r = _render(ctx, s)
        source = _source(ctx, s)
        report = build_risk_report(
            source={
                "title": source.title,
                "uploader": source.uploader,
                "url": source.url,
                "platform_license": source.platform_license,
                "rights_status": source.rights_status,
                "rights_note": source.rights_note,
            },
            profile=json.loads(r.profile_snapshot_json),
            plan=json.loads(r.plan_json) if r.plan_json else None,
            plan_engine=r.plan_engine,
            subtitles_translated=r.subtitles_are_translation,
            subtitles_enabled=bool(r.subtitles_json and json.loads(r.subtitles_json)),
            candidate=json.loads(r.candidate_snapshot_json) if r.candidate_snapshot_json else None,
            qc=json.loads(r.qc_json) if r.qc_json else None,
        )
        r.risk_report_json = json.dumps(report, ensure_ascii=False)
        s.commit()
    return {
        "reused_content": report["reused_content"]["level"],
        "transformation": report["transformation"]["level"],
        "blocking": False,
    }


RENDER_STEPS = {
    "creating_editorial_plan": creating_editorial_plan,
    "preparing_subtitles": preparing_subtitles,
    "rendering": rendering,
    "quality_check": quality_checking,
    "building_risk_report": building_risk_report,
}
