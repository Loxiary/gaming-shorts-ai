"""Étapes du job ``analyze_clips`` (Phase 3).

Chaque étape lit son entrée en base, écrit sa sortie (base + fichiers) et retourne un
résumé JSON. Les étapes sont reprenables : un proxy, des scènes ou des images déjà produits
sont réutilisés, et un extrait déjà évalué n'est jamais renvoyé à l'IA (pas de double coût).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.adapters.asr.faster_whisper import load_wav_16k_mono
from app.analysis.candidates import generate_windows
from app.analysis.judge import (
    BOUNDS_TOLERANCE,
    JudgeContext,
    JudgeInput,
    JudgeResult,
    signals_only_assessment,
)
from app.analysis.signals import Signals, compute_signals
from app.models import (
    CRITERIA,
    ApiUsage,
    ClipAnalysis,
    ClipCandidate,
    ClipScore,
    Project,
    SceneSegment,
    SourceMedia,
    Transcript,
    TranscriptSegment,
)
from app.services import budget
from app.services.analyses import apply_selection
from app.workers.context import StepContext
from app.workers.errors import StepError

logger = logging.getLogger("app.pipeline.analyze")

SCENE_THRESHOLD = 12.0
FRAME_WIDTH = 854


# --------------------------------------------------------------------------- utilitaires


def _analysis(ctx: StepContext, s: Session) -> ClipAnalysis:
    analysis = s.scalar(select(ClipAnalysis).where(ClipAnalysis.job_id == ctx.job_id))
    if analysis is None:
        raise StepError("Analyse introuvable pour ce job.")
    return analysis


def _source(ctx: StepContext, s: Session) -> SourceMedia:
    source = s.scalar(select(SourceMedia).where(SourceMedia.project_id == ctx.project_id))
    if source is None or not source.media_path:
        raise StepError("Vidéo source absente : relancez l'import.")
    return source


def _transcript(s: Session, source_id: str) -> Transcript:
    t = s.scalar(
        select(Transcript)
        .where(Transcript.source_media_id == source_id, Transcript.kind == "source")
        .order_by(Transcript.created_at.desc())
        .limit(1)
    )
    if t is None:
        raise StepError("Transcription absente : relancez l'import.")
    return t


def _segments(s: Session, transcript_id: str) -> list[TranscriptSegment]:
    return list(
        s.scalars(
            select(TranscriptSegment)
            .where(TranscriptSegment.transcript_id == transcript_id)
            .order_by(TranscriptSegment.position)
        )
    )


def _analysis_dir(ctx: StepContext) -> Path:
    return ctx.settings.subdir("projects") / ctx.project_id / "analysis"


def _snapshot(analysis: ClipAnalysis) -> dict[str, Any]:
    return json.loads(analysis.profile_snapshot_json)


def _add_note(s: Session, analysis: ClipAnalysis, note: str) -> None:
    notes = json.loads(analysis.notes_json) if analysis.notes_json else []
    if note not in notes:
        notes.append(note)
    analysis.notes_json = json.dumps(notes, ensure_ascii=False)
    s.commit()


def _load_signals(ctx: StepContext, analysis: ClipAnalysis) -> Signals:
    if not analysis.signals_path:
        raise StepError("Signaux absents : l'étape d'analyse audio n'a pas été exécutée.")
    path = ctx.settings.resolve_data_path(analysis.signals_path)
    return Signals.from_json(json.loads(path.read_text(encoding="utf-8")))


# --------------------------------------------------------------------------- 1. proxy


def preparing_proxy(ctx: StepContext) -> dict[str, Any]:
    with ctx.session_factory() as s:
        source = _source(ctx, s)
        media, duration, codec = (
            source.media_path,
            source.duration_seconds or 0.0,
            source.video_codec,
        )
    proxy = _analysis_dir(ctx) / f"proxy_{ctx.settings.analysis_proxy_height}p.mp4"
    tool = ctx.adapters.media
    if proxy.is_file():
        try:
            if abs(tool.probe(proxy).duration_seconds - duration) < 1.5:
                return {"proxy_path": ctx.settings.to_relative(proxy), "reused": True}
        except StepError:
            pass
    assert media is not None
    tool.make_proxy(
        ctx.settings.resolve_data_path(media),
        proxy,
        ctx.settings.analysis_proxy_height,
        duration,
        ctx.report_progress,
        ctx.check_cancel,
        video_codec=codec,
    )
    return {
        "proxy_path": ctx.settings.to_relative(proxy),
        "size_bytes": proxy.stat().st_size,
        "reused": False,
    }


# --------------------------------------------------------------------------- 2. scènes


def detecting_scenes(ctx: StepContext) -> dict[str, Any]:
    with ctx.session_factory() as s:
        source = _source(ctx, s)
        source_id, duration = source.id, source.duration_seconds or 0.0
        existing = s.scalar(
            select(SceneSegment.id).where(SceneSegment.source_media_id == source_id)
        )
    if existing:
        with ctx.session_factory() as s:
            n = len(
                list(
                    s.scalars(
                        select(SceneSegment.id).where(SceneSegment.source_media_id == source_id)
                    )
                )
            )
        return {"scenes": n, "reused": True}

    proxy = _analysis_dir(ctx) / f"proxy_{ctx.settings.analysis_proxy_height}p.mp4"
    cuts = ctx.adapters.media.detect_scenes(
        proxy, duration, SCENE_THRESHOLD, ctx.report_progress, ctx.check_cancel
    )
    bounds = [(0.0, None)] + [(t, score) for t, score in cuts if 0.5 < t < duration - 0.5]
    with ctx.session_factory() as s:
        s.execute(delete(SceneSegment).where(SceneSegment.source_media_id == source_id))
        for i, (start, score) in enumerate(bounds):
            end = bounds[i + 1][0] if i + 1 < len(bounds) else duration
            if end > start:
                s.add(
                    SceneSegment(
                        source_media_id=source_id,
                        position=i,
                        start_seconds=start,
                        end_seconds=end,
                        cut_score=score,
                    )
                )
        s.commit()
    return {"scenes": len(bounds), "cuts": len(bounds) - 1, "threshold": SCENE_THRESHOLD}


# --------------------------------------------------------------------------- 3. audio / signaux


def analyzing_audio(ctx: StepContext) -> dict[str, Any]:
    with ctx.session_factory() as s:
        analysis = _analysis(ctx, s)
        source = _source(ctx, s)
        if not source.audio_path:
            raise StepError("Audio extrait absent : relancez l'import.")
        audio_path = ctx.settings.resolve_data_path(source.audio_path)
        duration = source.duration_seconds or 0.0
        transcript = _transcript(s, source.id)
        words: list[tuple[float, float]] = []
        for seg in _segments(s, transcript.id):
            seg_words = json.loads(seg.words_json) if seg.words_json else []
            words += [(w["start"], w["end"]) for w in seg_words] or [
                (seg.start_seconds, seg.end_seconds)
            ]
        cuts = [
            sc.start_seconds
            for sc in s.scalars(
                select(SceneSegment).where(SceneSegment.source_media_id == source.id)
            )
            if sc.start_seconds > 0
        ]
        analysis_id = analysis.id
    ctx.report_progress(0.2, "Lecture de l'audio…")
    signals = compute_signals(load_wav_16k_mono(audio_path), words, cuts, duration)
    out = _analysis_dir(ctx) / analysis_id / "signals.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(signals.to_json()), encoding="utf-8")
    with ctx.session_factory() as s:
        _analysis(ctx, s).signals_path = ctx.settings.to_relative(out)
        s.commit()
    return {
        "audio_peaks": len(signals.audio_peaks),
        "speech_seconds": sum(1 for x in signals.speech_rate if x > 0),
        "words": len(words),
        "scene_cuts": len(cuts),
    }


# --------------------------------------------------------------------------- 4. candidats


_SENTENCE_END = (".", "!", "?", "…")


def sentence_bounds(segments: list[TranscriptSegment]) -> tuple[list[float], list[float]]:
    """Débuts et fins de phrases d'après la ponctuation des mots horodatés.

    Whisper coupe souvent ses segments au milieu d'une phrase : caler un extrait sur un
    segment ne garantit donc pas un début compréhensible. Repli sur les bornes de segments
    si la transcription n'a pas de ponctuation exploitable.
    """
    starts: list[float] = []
    ends: list[float] = []
    previous_closed = True
    for seg in segments:
        words = json.loads(seg.words_json) if seg.words_json else []
        if not words:
            words = [{"start": seg.start_seconds, "end": seg.end_seconds, "word": seg.text}]
        for w in words:
            text = str(w.get("word", "")).strip()
            if not text:
                continue
            if previous_closed:
                starts.append(round(float(w["start"]), 2))
            previous_closed = text.endswith(_SENTENCE_END)
            if previous_closed:
                ends.append(round(float(w["end"]), 2))
    if len(starts) < 2 or len(ends) < 2:
        starts = [round(seg.start_seconds, 2) for seg in segments]
        ends = [round(seg.end_seconds, 2) for seg in segments]
    return starts, ends


def transcript_for_window(
    segments: list[TranscriptSegment], start: float, end: float, context: float
) -> list[tuple[float, float, str]]:
    """Transcription autour d'un extrait, présentée PHRASE PAR PHRASE et coupée aux bornes.

    Les segments Whisper coupent arbitrairement les phrases (« And also the » / « world
    was… ») : envoyés tels quels, l'IA croit que l'extrait commence ou finit au milieu d'une
    phrase. On reconstruit donc des lignes à partir des mots horodatés : une nouvelle ligne
    commence après une ponctuation de fin de phrase, ou quand on franchit une borne de
    l'extrait (les parties hors extrait sont ensuite marquées comme telles dans le prompt).
    """
    words: list[tuple[float, float, str]] = []
    for seg in segments:
        if seg.end_seconds <= start - context or seg.start_seconds >= end + context:
            continue
        seg_words = json.loads(seg.words_json) if seg.words_json else []
        if not seg_words:  # pas de mots horodatés : le segment entier tient lieu de mot
            seg_words = [{"start": seg.start_seconds, "end": seg.end_seconds, "word": seg.text}]
        for w in seg_words:
            ws, we = float(w["start"]), float(w["end"])
            if we > start - context and ws < end + context:
                words.append((ws, we, str(w["word"])))

    def part(ws: float, we: float) -> int:
        middle = (ws + we) / 2
        return 0 if middle < start else 2 if middle >= end else 1

    lines: list[tuple[float, float, str]] = []
    current: list[tuple[float, float, str]] = []
    current_part = -1
    for ws, we, text in words:
        p_ = part(ws, we)
        if current and p_ != current_part:
            lines.append(_join(current))
            current = []
        current.append((ws, we, text))
        current_part = p_
        if text.strip().endswith(_SENTENCE_END):
            lines.append(_join(current))
            current = []
    if current:
        lines.append(_join(current))
    return lines


def _join(words: list[tuple[float, float, str]]) -> tuple[float, float, str]:
    return words[0][0], words[-1][1], "".join(w for _, _, w in words).strip()


def _excerpt(segments: list[TranscriptSegment], start: float, end: float) -> str:
    return " ".join(
        text
        for a, b, text in transcript_for_window(segments, start, end, context=0.0)
        if start <= (a + b) / 2 < end
    ).strip()


def generating_candidates(ctx: StepContext) -> dict[str, Any]:
    with ctx.session_factory() as s:
        analysis = _analysis(ctx, s)
        source = _source(ctx, s)
        profile = _snapshot(analysis)
        segments = _segments(s, _transcript(s, source.id).id)
        cuts = [
            sc.start_seconds
            for sc in s.scalars(
                select(SceneSegment).where(SceneSegment.source_media_id == source.id)
            )
            if sc.start_seconds > 0
        ]
        signals = _load_signals(ctx, analysis)
        duration = source.duration_seconds or signals.duration
        sentence_starts, sentence_ends = sentence_bounds(segments)

        windows = generate_windows(
            duration=duration,
            interest=signals.interest,
            sentence_starts=sentence_starts,
            sentence_ends=sentence_ends,
            scene_cuts=cuts,
            min_duration=profile["min_duration"],
            max_duration=profile["max_duration"],
            max_candidates=profile["max_candidates"],
        )
        s.execute(delete(ClipCandidate).where(ClipCandidate.analysis_id == analysis.id))
        for i, w in enumerate(windows):
            a, b = int(w.start), max(int(w.end), int(w.start) + 1)
            peaks = [p for p in signals.audio_peaks if w.start <= p <= w.end]
            speech = signals.speech_rate[a:b]
            s.add(
                ClipCandidate(
                    analysis_id=analysis.id,
                    position=i,
                    start_seconds=w.start,
                    end_seconds=w.end,
                    peak_seconds=w.peak,
                    signal_score=round(w.score, 4),
                    transcript_excerpt=_excerpt(segments, w.start, w.end),
                    signals_json=json.dumps(
                        {
                            "audio_peaks": peaks,
                            "speech_coverage": round(
                                sum(1 for x in speech if x > 0) / max(len(speech), 1), 3
                            ),
                            "words": int(sum(speech)),
                            "scene_cuts": sum(1 for c in cuts if w.start <= c <= w.end),
                            "interest_mean": round(
                                sum(signals.interest[a:b]) / max(len(signals.interest[a:b]), 1), 3
                            ),
                        }
                    ),
                )
            )
        s.commit()
        if not windows:
            reason = (
                f"La vidéo dure {duration:.0f} s, moins que la durée minimale de "
                f"{profile['min_duration']:.0f} s : aucun extrait ne peut être proposé."
                if duration < profile["min_duration"]
                else "Aucun extrait cohérent d'au moins "
                f"{profile['min_duration']:.0f} s n'a été trouvé."
            )
            _add_note(s, analysis, reason)
    return {"candidates": len(windows)}


# --------------------------------------------------------------------------- 5. images


def _frame_times(c: ClipCandidate, signals: Signals, n: int) -> list[float]:
    if n <= 0:
        return []
    start, end = c.start_seconds, c.end_seconds - 0.5
    a, b = int(start), max(int(end), int(start) + 1)
    interest = signals.interest[a:b]
    ranked = sorted(range(len(interest)), key=lambda i: -interest[i])[:3]
    wanted = [start + 1.5] + [a + i + 0.5 for i in ranked]
    wanted += [p for p in signals.audio_peaks if start <= p <= end][:2]
    step = (end - start) / max(n, 1)
    wanted += [start + step * (i + 0.5) for i in range(n)]
    times: list[float] = []
    for t in wanted:
        t = min(max(t, start), end)
        if all(abs(t - x) >= 4.0 for x in times):
            times.append(round(t, 2))
        if len(times) >= n:
            break
    return sorted(times)


def sampling_frames(ctx: StepContext) -> dict[str, Any]:
    with ctx.session_factory() as s:
        analysis = _analysis(ctx, s)
        if not analysis.use_vision or ctx.settings.frames_per_candidate == 0:
            return {"skipped": True, "reason": "vision désactivée pour ce profil"}
        signals = _load_signals(ctx, analysis)
        candidates = list(
            s.scalars(
                select(ClipCandidate)
                .where(ClipCandidate.analysis_id == analysis.id)
                .order_by(ClipCandidate.position)
            )
        )
        analysis_id = analysis.id
    proxy = _analysis_dir(ctx) / f"proxy_{ctx.settings.analysis_proxy_height}p.mp4"
    frames_dir = _analysis_dir(ctx) / analysis_id / "frames"
    total = 0
    for k, c in enumerate(candidates):
        ctx.check_cancel()
        if c.frames_json and all(
            ctx.settings.resolve_data_path(f["path"]).is_file() for f in json.loads(c.frames_json)
        ):
            total += len(json.loads(c.frames_json))
            continue
        frames = []
        for t in _frame_times(c, signals, ctx.settings.frames_per_candidate):
            dst = frames_dir / f"{c.position:02d}_{int(t * 10):06d}.jpg"
            ctx.adapters.media.extract_frame(proxy, t, dst, FRAME_WIDTH)
            frames.append({"t": t, "path": ctx.settings.to_relative(dst)})
        total += len(frames)
        with ctx.session_factory() as s:
            row = s.get(ClipCandidate, c.id)
            assert row is not None
            row.frames_json = json.dumps(frames)
            s.commit()
        ctx.report_progress((k + 1) / len(candidates), f"{k + 1}/{len(candidates)} extraits")
    return {"frames": total, "candidates": len(candidates)}


# --------------------------------------------------------------------------- 6. évaluation


def _av_score(source: SourceMedia) -> float:
    h, fps = source.height or 0, source.fps or 0
    base = 8 if h >= 1080 else 6 if h >= 720 else 4
    return min(10.0, base + (1 if fps >= 50 else 0))


def _save_assessment(
    s: Session,
    c: ClipCandidate,
    result_status: str,
    assessment,
    model: str | None,  # type: ignore[no-untyped-def]
    raw: str | None,
    duration: float,
    min_d: float,
    max_d: float,
) -> None:
    warnings = list(assessment.warnings)
    new_start, new_end = assessment.suggested_start, assessment.suggested_end
    if (new_start, new_end) != (c.start_seconds, c.end_seconds):
        ok = (
            abs(new_start - c.start_seconds) <= BOUNDS_TOLERANCE + 0.01
            and abs(new_end - c.end_seconds) <= BOUNDS_TOLERANCE + 0.01
            and min_d <= new_end - new_start <= max_d
            and 0 <= new_start < new_end <= duration
        )
        if ok:
            c.start_seconds, c.end_seconds = round(new_start, 2), round(new_end, 2)
        else:
            warnings.append(
                "Bornes suggérées par l'IA ignorées (hors des limites autorisées) : "
                "l'extrait garde ses bornes initiales."
            )
    if not assessment.self_contained:
        warnings.append("Peut nécessiter du contexte pour être compris (estimation).")
    c.status = result_status
    c.summary = assessment.summary
    c.reason = assessment.reason
    c.events_json = json.dumps([e.model_dump() for e in assessment.key_events], ensure_ascii=False)
    c.warnings_json = json.dumps(warnings, ensure_ascii=False)
    c.confidence = max(0.0, min(1.0, assessment.confidence))
    c.llm_model = model
    c.raw_response_json = raw
    c.error_message = None
    s.execute(delete(ClipScore).where(ClipScore.candidate_id == c.id))
    for key in CRITERIA:
        crit = getattr(assessment, key)
        s.add(
            ClipScore(
                candidate_id=c.id,
                criterion=key,
                score=float(crit.score),
                justification=crit.justification,
            )
        )


def scoring_candidates(ctx: StepContext) -> dict[str, Any]:
    with ctx.session_factory() as s:
        analysis = _analysis(ctx, s)
        source = _source(ctx, s)
        project = s.get(Project, ctx.project_id)
        profile = _snapshot(analysis)
        signals = _load_signals(ctx, analysis)
        segments = _segments(s, _transcript(s, source.id).id)
        requested = analysis.engine or "auto"
        analysis_id = analysis.id
        candidate_ids = list(
            s.scalars(
                select(ClipCandidate.id)
                .where(ClipCandidate.analysis_id == analysis_id, ClipCandidate.status == "pending")
                .order_by(ClipCandidate.position)
            )
        )
        context = JudgeContext(
            video_title=source.title,
            creator=source.uploader,
            game=project.game if project else None,
            language=profile["output_language"],
            profile_name=profile["name"],
            editorial_focus=profile.get("editorial_focus"),
            min_duration=profile["min_duration"],
            max_duration=profile["max_duration"],
            video_duration=source.duration_seconds or signals.duration,
        )
        av_score = _av_score(source)
        duration = context.video_duration
        api_on = budget.api_enabled(s)

    judge = ctx.adapters.judge
    configured = bool(judge and getattr(judge, "configured", True))
    engine = "signals"
    if requested in {"auto", "llm"}:
        if configured and api_on:
            engine = "llm"
        elif requested == "llm":
            raise StepError(
                "Évaluation par IA impossible : "
                + (
                    "clé API absente (ANTHROPIC_API_KEY dans .env)."
                    if not configured
                    else "l'API est désactivée dans les paramètres."
                )
            )
        else:
            with ctx.session_factory() as s:
                _add_note(
                    s,
                    _analysis(ctx, s),
                    "Évaluation sans IA ("
                    + ("clé API absente" if not configured else "API désactivée")
                    + ") : notes approximatives fondées sur les signaux.",
                )
    with ctx.session_factory() as s:
        a = _analysis(ctx, s)
        a.engine = engine
        a.llm_model = judge.model if engine == "llm" and judge else None
        s.commit()

    counts = {"scored": 0, "signals_only": 0, "refused": 0, "failed": 0}
    for k, cid in enumerate(candidate_ids):
        ctx.check_cancel()
        with ctx.session_factory() as s:
            c = s.get(ClipCandidate, cid)
            assert c is not None
            frames = [
                (f["t"], ctx.settings.resolve_data_path(f["path"]))
                for f in (json.loads(c.frames_json) if c.frames_json else [])
            ]
            item = JudgeInput(
                start=c.start_seconds,
                end=c.end_seconds,
                transcript=transcript_for_window(
                    segments, c.start_seconds, c.end_seconds, context=10.0
                ),
                signals_summary=_signals_summary(c),
                frames=frames,
            )

        if engine == "llm" and judge is not None:
            try:
                result = judge.judge(context, item, _budget_checker(ctx), _usage_recorder(ctx, cid))
            except budget.BudgetExceeded as exc:
                engine = "signals"
                with ctx.session_factory() as s:
                    a = _analysis(ctx, s)
                    a.engine = "mixed" if counts["scored"] else "signals"
                    _add_note(s, a, f"{exc} Extraits restants évalués par signaux (sans IA).")
                result = None
        else:
            result = None

        with ctx.session_factory() as s:
            c = s.get(ClipCandidate, cid)
            assert c is not None
            if result is None:
                assessment = _signals_assessment(c, signals, segments, av_score, context.language)
                _save_assessment(
                    s,
                    c,
                    "signals_only",
                    assessment,
                    None,
                    None,
                    duration,
                    context.min_duration,
                    context.max_duration,
                )
                counts["signals_only"] += 1
            elif result.status == "scored" and result.assessment is not None:
                _save_assessment(
                    s,
                    c,
                    "scored",
                    result.assessment,
                    result.model,
                    result.raw,
                    duration,
                    context.min_duration,
                    context.max_duration,
                )
                counts["scored"] += 1
            else:
                c.status = result.status
                c.error_message = result.error
                c.llm_model = result.model
                c.raw_response_json = result.raw
                counts[result.status] = counts.get(result.status, 0) + 1
            s.commit()
        ctx.report_progress(
            (k + 1) / max(len(candidate_ids), 1), f"{k + 1}/{len(candidate_ids)} extraits évalués"
        )

    with ctx.session_factory() as s:
        a = _analysis(ctx, s)
        cost = a.cost_usd
    return {"engine": engine, **counts, "cost_usd": round(cost, 4)}


def _signals_summary(c: ClipCandidate) -> str:
    sig = json.loads(c.signals_json) if c.signals_json else {}
    peaks = ", ".join(f"{p:.0f} s" for p in sig.get("audio_peaks", [])[:6]) or "aucun"
    return (
        f"pics d'énergie sonore à : {peaks} ; parole sur {sig.get('speech_coverage', 0):.0%} "
        f"de l'extrait ({sig.get('words', 0)} mots) ; {sig.get('scene_cuts', 0)} changements "
        f"de scène ; intérêt moyen mesuré {sig.get('interest_mean', 0):.2f} sur 1."
    )


def _signals_assessment(c, signals: Signals, segments, av_score: float, language: str):  # type: ignore[no-untyped-def]
    starts_list, ends_list = sentence_bounds(segments)
    starts, ends = set(starts_list), set(ends_list)
    first = next(
        (
            seg.text
            for seg in segments
            if seg.end_seconds > c.start_seconds and seg.start_seconds < c.end_seconds
        ),
        None,
    )
    return signals_only_assessment(
        start=c.start_seconds,
        end=c.end_seconds,
        interest=signals.interest,
        excitement=signals.excitement,
        speech_rate=signals.speech_rate,
        scene_density=signals.scene_density,
        boundary_on_sentence=(round(c.start_seconds, 2) in starts, round(c.end_seconds, 2) in ends),
        first_line=first,
        av_score=av_score,
        language=language,
    )


def _budget_checker(ctx: StepContext):  # type: ignore[no-untyped-def]
    def check(estimate: float) -> None:
        with ctx.session_factory() as s:
            budget.check_budget(s, ctx.settings, estimate)

    return check


def _usage_recorder(ctx: StepContext, candidate_id: str):  # type: ignore[no-untyped-def]
    def record(result: JudgeResult, images: int) -> None:
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
                    purpose="clip_scoring",
                    project_id=ctx.project_id,
                    job_id=ctx.job_id,
                    candidate_id=candidate_id,
                    input_tokens=u.input_tokens,
                    output_tokens=u.output_tokens,
                    cache_read_tokens=u.cache_read_tokens,
                    cache_write_tokens=u.cache_write_tokens,
                    images=images,
                    cost_usd=round(cost, 6),
                    status={"scored": "ok"}.get(result.status, result.status),
                    request_id=result.request_id,
                    detail=result.error,
                )
            )
            a = _analysis(ctx, s)
            a.cost_usd = (a.cost_usd or 0) + cost
            s.commit()
        ctx.heartbeat()

    return record


# --------------------------------------------------------------------------- 7. sélection


def selecting_clips(ctx: StepContext) -> dict[str, Any]:
    from app.services.analyses import get_analysis

    with ctx.session_factory() as s:
        analysis = get_analysis(s, _analysis(ctx, s).id)
        selected = apply_selection(s, analysis)
        return {
            "selected": selected,
            "candidates": len(analysis.candidates),
            "threshold": analysis.threshold,
        }


ANALYZE_STEPS = {
    "preparing_proxy": preparing_proxy,
    "detecting_scenes": detecting_scenes,
    "analyzing_audio": analyzing_audio,
    "generating_candidates": generating_candidates,
    "sampling_frames": sampling_frames,
    "scoring_candidates": scoring_candidates,
    "selecting_clips": selecting_clips,
}
