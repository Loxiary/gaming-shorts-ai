"""Étapes audio et facecam du job ``render_clip`` (Phase 5).

- detecting_facecam : visage persistant dans un coin → recadrage pour l'exclure.
- preparing_audio : détection de la musique d'origine (PANNs) et atténuation par séparation
  de sources (Demucs), narration de synthèse (Piper) décidée par l'IA, musique de la
  bibliothèque locale (licence confirmée uniquement), mixage et aperçu audio.

Un modèle absent ne fait jamais échouer le montage : la fonction est sautée et le rapport
le dit explicitement (il alimente le rapport de risques).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
from sqlalchemy import select

from app.audio import mix
from app.models import MusicTrack, Project
from app.models_registry import PIPER_VOICES
from app.render import editorial as ed
from app.render.facecam import Face, analyze_detections
from app.render.profanity import censor_text
from app.workers.context import StepContext
from app.workers.errors import StepError
from app.workers.pipeline.render import (
    _render,
    _sentences,
    _source,
    _workdir,
    building_risk_report,
    creating_editorial_plan,
    preparing_subtitles,
    quality_checking,
    rendering,
)

MUSIC_THRESHOLD = 0.4  # probabilité PANNs « Music » par seconde
MUSIC_MIN_RATIO = 0.1  # musique sur au moins 10 % des secondes → considérée présente
FACECAM_FRAMES = 10
DUCK_GAME_UNDER_NARRATION_DB = 9.0
DUCK_MUSIC_UNDER_VOICE_DB = 8.0
TITLE_VOICE_START = 0.2  # la voix lit le titre dès l'ouverture
BLEEP_PAD = 0.04  # marge autour du mot couvert par le bip (horodatage Whisper approximatif)


def has_profanity(text: str) -> bool:
    return censor_text(text)[1] > 0


def _toolkit(ctx: StepContext):  # type: ignore[no-untyped-def]
    return getattr(ctx.adapters, "audio", None)


# --------------------------------------------------------------------------- facecam


def _frame_source(ctx: StepContext, src_path: Path) -> Path:
    """Proxy d'analyse (H.264 480p, décodage rapide) s'il existe, sinon la source."""
    proxy = (
        ctx.settings.subdir("projects")
        / ctx.project_id
        / "analysis"
        / f"proxy_{ctx.settings.analysis_proxy_height}p.mp4"
    )
    return proxy if proxy.is_file() else src_path


def detecting_facecam(ctx: StepContext) -> dict[str, Any]:
    with ctx.session_factory() as s:
        r = _render(ctx, s)
        profile = json.loads(r.profile_snapshot_json)
        src_path = ctx.settings.resolve_data_path(_source(ctx, s).media_path or "")
        start, end, render_id = r.start_seconds, r.end_seconds, r.id
    mode = profile.get("facecam_mode", "crop")
    tk = _toolkit(ctx)
    if mode == "off":
        result: dict[str, Any] = {"status": "disabled", "crop": None, "warning": None}
    elif tk is None or not tk.has("yunet"):
        result = {
            "status": "unavailable",
            "crop": None,
            "warning": "Détecteur de visages absent (python -m app.cli.models download yunet) : "
            "présence d'un facecam non vérifiée.",
        }
    else:
        import cv2

        video = _frame_source(ctx, src_path)
        frames_dir = _workdir(ctx, render_id) / "facecam"
        span = max(end - start - 1.0, 0.1)
        detections: list[list[Face]] = []
        for i in range(FACECAM_FRAMES):
            ctx.check_cancel()
            t = start + 0.5 + span * (i + 0.5) / FACECAM_FRAMES
            dst = frames_dir / f"{i:02d}.jpg"
            try:
                ctx.adapters.media.extract_frame(video, t, dst, 640)
            except Exception:  # noqa: BLE001 - une image manquante ne bloque pas la détection
                continue
            img = cv2.imread(str(dst))
            if img is None:
                continue
            detections.append(tk.detect_faces(img) or [])
            ctx.report_progress((i + 1) / FACECAM_FRAMES, f"Recherche d'un facecam ({i + 1}/10)")
        result = analyze_detections(detections)
        if result["status"] == "detected" and not result.get("crop"):
            result["status"] = "detected_not_cropped"
    result["mode"] = mode
    if profile.get("layout") == "focus":
        result["focus"] = _focus_track(ctx, src_path, start, end, render_id, tk, result)
    with ctx.session_factory() as s:
        r = _render(ctx, s)
        r.facecam_json = json.dumps(result, ensure_ascii=False)
        s.commit()
    return {
        "status": result["status"],
        "crop": result.get("crop"),
        "loss": result.get("loss"),
        "presence": result.get("presence"),
    }


def _focus_track(  # type: ignore[no-untyped-def]
    ctx: StepContext, src_path: Path, start: float, end: float, render_id: str, tk, fc: dict
) -> list[list[float]]:
    """Disposition « gros plan » : trajectoire du cadre qui suit le visage à l'écran."""
    if tk is None or not tk.has("yunet"):
        return []
    import cv2

    from app.render.focus import SAMPLE_EVERY, focus_track

    video = _frame_source(ctx, src_path)
    frames_dir = _workdir(ctx, render_id) / "focus"
    samples: list[tuple[float, list[Face]]] = []
    n = max(2, int((end - start) / SAMPLE_EVERY))
    for i in range(n):
        ctx.check_cancel()
        rel = (end - start) * (i + 0.5) / n
        dst = frames_dir / f"{i:03d}.jpg"
        try:
            ctx.adapters.media.extract_frame(video, start + rel, dst, 640)
        except Exception:  # noqa: BLE001 - image manquante : la position précédente est gardée
            continue
        img = cv2.imread(str(dst))
        if img is not None:
            samples.append((rel, tk.detect_faces(img) or []))
        ctx.report_progress((i + 1) / n, f"Cadrage sur les visages ({i + 1}/{n})")
    exclude = fc.get("cam_box") if fc.get("status") in ("detected", "uncertain") else None
    return [[t, x] for t, x in focus_track(samples, exclude)]


# --------------------------------------------------------------------------- audio


def _voice_for(profile: dict[str, Any], tk) -> tuple[str | None, str | None]:  # type: ignore[no-untyped-def]
    """Voix du profil si elle parle la langue de sortie, sinon une voix installée qui la parle."""
    language = profile.get("output_language", "fr")
    wanted = profile.get("narration_voice", "fr_FR-siwis-medium")
    installed = tk.voices()
    if wanted in installed and wanted.split("_")[0] == language:
        return wanted, None
    same_lang = [v for v in installed if v.split("_")[0] == language]
    if same_lang:
        return same_lang[
            0
        ], f"Voix « {wanted} » remplacée par « {same_lang[0]} » (langue {language})."
    return None, f"Aucune voix installée pour la langue « {language} » : narration abandonnée."


def _pick_track(tracks: list[MusicTrack], mood: str, seed: str) -> MusicTrack | None:
    if not tracks:
        return None
    matching = [t for t in tracks if mood and mood.lower() in t.mood_list] or tracks
    matching.sort(key=lambda t: t.id)
    idx = int(hashlib.sha1(seed.encode()).hexdigest(), 16) % len(matching)
    return matching[idx]


def _music_credit(t: MusicTrack) -> str:
    parts = [f"Musique : « {t.title or Path(t.file_path).stem} »"]
    if t.artist:
        parts.append(f"— {t.artist}")
    parts.append(f"({t.license})")
    if t.source_url:
        parts.append(t.source_url)
    return " ".join(parts)


def preparing_audio(ctx: StepContext) -> dict[str, Any]:
    with ctx.session_factory() as s:
        r = _render(ctx, s)
        profile = json.loads(r.profile_snapshot_json)
        plan = ed.EditorialPlan.model_validate_json(r.plan_json or "{}")
        engine = r.plan_engine
        source = _source(ctx, s)
        src_path = ctx.settings.resolve_data_path(source.media_path or "")
        sentences, _ = _sentences(s, source.id, r.start_seconds, r.end_seconds)
        start, duration, render_id = r.start_seconds, r.end_seconds - r.start_seconds, r.id
        tracks = [t for t in s.scalars(select(MusicTrack)) if t.usable]
        for t in tracks:
            s.expunge(t)
    tk = _toolkit(ctx)
    workdir = _workdir(ctx, render_id)
    sr = mix.SR
    n = int(round(duration * sr))
    notes: list[str] = []
    credits: list[dict[str, str]] = []

    ctx.report_progress(0.02, "Extraction de l'audio de l'extrait…")
    try:
        game = mix.fit(mix.read_audio(src_path, start=start, duration=duration), n)
    except RuntimeError as exc:
        raise StepError(f"Lecture de l'audio impossible : {exc}") from exc
    speech = mix.merge_intervals([(a, b) for s_ in sentences for (a, b, _) in s_.words], gap=0.3)

    # 1. Musique d'origine ------------------------------------------------------------
    smode = profile.get("source_music_mode", "attenuate")
    reduction = float(profile.get("source_music_reduction_db", 15.0))
    source_music: dict[str, Any] = {"mode": smode, "status": "disabled", "attenuated": False}
    detector = tk.music_detector() if (tk is not None and smode != "off") else None
    if smode != "off" and detector is None:
        source_music["status"] = "unavailable"
        notes.append("Détecteur de musique absent : musique d'origine non analysée.")
    elif detector is not None:
        ctx.check_cancel()
        ctx.report_progress(0.08, "Détection de la musique d'origine…")
        tags = detector.tag(
            mix.read_audio(src_path, sr=16_000, channels=1, start=start, duration=duration)[0]
        )
        ratio = sum(1 for p in tags.music if p >= MUSIC_THRESHOLD) / max(len(tags.music), 1)
        source_music.update(
            status="detected" if ratio >= MUSIC_MIN_RATIO else "none",
            ratio=round(ratio, 3),
            mean=round(float(np.mean(tags.music)), 3) if tags.music else 0.0,
            threshold=MUSIC_THRESHOLD,
            per_second=[round(p, 2) for p in tags.music],
        )
        if smode == "attenuate" and ratio >= MUSIC_MIN_RATIO:
            sep = tk.separator()
            if sep is None:
                notes.append("Modèle de séparation absent : musique d'origine non atténuée.")
            else:
                ctx.check_cancel()
                ctx.report_progress(
                    0.15, f"Atténuation de la musique (séparation, ~{duration * 0.6:.0f} s)…"
                )
                from app.audio.separation import music_gain_curve, remix_attenuated

                stems = sep.separate(game)
                gain = music_gain_curve(tags.music, n, sr, MUSIC_THRESHOLD, reduction)
                game = mix.fit(remix_attenuated(stems, gain), n).astype(np.float32)
                ctx.check_cancel()
                ctx.report_progress(0.6, "Vérification de la musique résiduelle…")
                mix.write_wav(workdir / "game_attenuated.wav", game)
                residual = detector.tag(
                    mix.read_audio(workdir / "game_attenuated.wav", sr=16_000, channels=1)[0]
                )
                res_ratio = sum(1 for p in residual.music if p >= MUSIC_THRESHOLD) / max(
                    len(residual.music), 1
                )
                source_music.update(
                    attenuated=True,
                    reduction_db=reduction,
                    residual_ratio=round(res_ratio, 3),
                    residual_mean=round(float(np.mean(residual.music)), 3),
                )
    music_kept = source_music["status"] == "detected" and not source_music["attenuated"]

    # 2. Narration : titre lu au début, puis lignes de l'IA dans les silences ------------
    nmode = profile.get("narration_mode", "auto")
    narration_info: dict[str, Any] = {"mode": nmode, "status": "disabled", "lines": []}
    voice_track = np.zeros((2, n), dtype=np.float32)
    narration_iv: list[tuple[float, float]] = []
    title = plan.hook_text.strip()
    want_title = bool(profile.get("narration_title", True) and title and engine == "llm")
    want_lines = bool(engine == "llm" and plan.narration_needed and plan.narration)
    if nmode == "auto":
        voice = None
        if want_title or want_lines:
            if tk is None:
                narration_info["status"] = "unavailable"
                notes.append("Synthèse vocale indisponible : narration abandonnée.")
            else:
                voice, note = _voice_for(profile, tk)
                if note:
                    notes.append(note)
                if voice is None:
                    narration_info["status"] = "unavailable"
        elif engine != "llm":
            narration_info["status"] = "skipped"
            notes.append("Plan sans IA : pas de narration (aucun texte factuel vérifiable).")
        else:
            narration_info.update(status="not_needed", reason=plan.narration_reason)
        if voice is not None:
            ctx.report_progress(0.7, "Synthèse de la narration…")
            speed = float(profile.get("narration_speed", 1.0))

            def put(path: Path, t: float) -> None:
                audio = mix.read_audio(path)
                a0 = int(t * sr)
                seg = audio[:, : max(0, min(audio.shape[1], n - a0))]
                voice_track[:, a0 : a0 + seg.shape[1]] += seg

            busy = list(speech)
            if want_title and not has_profanity(title):
                # Lecture du titre en ouverture : seule intervention autorisée sur la parole
                # d'origine (le jeu est baissé dessous), car elle présente le short.
                out = tk.tts().synthesize(
                    title, voice, workdir / "narration" / "title.wav", speed=speed
                )
                put(out.path, TITLE_VOICE_START)
                iv = (TITLE_VOICE_START, TITLE_VOICE_START + out.duration)
                narration_iv.append(iv)
                busy.append(iv)
                narration_info["title"] = {"text": title, "duration": round(out.duration, 2)}
            elif want_title:
                notes.append("Titre non lu : il contient un mot grossier masqué.")
            placed: list[mix.PlacedLine] = []
            dropped: list[str] = []
            if want_lines:
                spoken: list[tuple[float, float, str]] = []
                paths: dict[str, Path] = {}
                for i, line in enumerate(plan.narration):
                    ctx.check_cancel()
                    out = tk.tts().synthesize(
                        line.text, voice, workdir / "narration" / f"{i:02d}.wav", speed=speed
                    )
                    spoken.append((line.t, out.duration, line.text))
                    paths[line.text] = out.path
                placed, dropped = mix.place_narration(
                    spoken, mix.merge_intervals(busy, gap=0), duration
                )
                for pl in placed:
                    put(paths[pl.text], pl.t)
                    narration_iv.append((pl.t, pl.t + pl.duration))
            spoke = bool(placed) or "title" in narration_info
            narration_info.update(
                status="added" if spoke else "dropped" if dropped else "not_needed",
                voice=voice,
                reason=plan.narration_reason,
                lines=[
                    {
                        "t": round(pl.t, 2),
                        "duration": round(pl.duration, 2),
                        "text": pl.text,
                        "moved": pl.moved,
                    }
                    for pl in placed
                ],
                dropped=dropped,
            )
            if dropped:
                notes.append(
                    f"{len(dropped)} ligne(s) de narration abandonnée(s) : aucun silence "
                    "assez long pour ne pas couvrir la parole d'origine."
                )
            credit = PIPER_VOICES[voice].credit
            if spoke and credit:
                credits.append({"kind": "voice", "text": credit})

    # 2 bis. Bip sur les mots grossiers prononcés (horodatage des mots de la transcription).
    bleeps: list[tuple[float, float]] = []
    if profile.get("bleep_profanity", True):
        bleeps = [
            (max(a0 - BLEEP_PAD, 0.0), min(b0 + BLEEP_PAD, duration))
            for s_ in sentences
            for (a0, b0, w) in s_.words
            if has_profanity(w)
        ]
        if bleeps:
            game = game * mix.envelope(n, sr, bleeps, 60.0, ramp=0.01)
            game = game + mix.beep_track(bleeps, n, sr)
    bleep_info = {
        "enabled": bool(profile.get("bleep_profanity", True)),
        "count": len(bleeps),
        "times": [round(x, 2) for x, _ in bleeps],
    }

    # 3. Musique ajoutée ---------------------------------------------------------------
    mmode = profile.get("music_mode", "suggest")
    music_info: dict[str, Any] = {"mode": mmode, "status": "disabled"}
    music_track = np.zeros((2, n), dtype=np.float32)
    if mmode == "library":
        if music_kept:
            music_info["status"] = "skipped"
            notes.append("Musique d'origine conservée : aucune musique ajoutée par-dessus.")
        elif engine == "llm" and not plan.music_mood:
            music_info["status"] = "not_needed"
        elif not tracks:
            music_info["status"] = "empty_library"
            notes.append(
                "Aucune musique utilisable : ajoutez des morceaux avec leur licence dans la "
                "bibliothèque musicale."
            )
        else:
            track = _pick_track(tracks, plan.music_mood, render_id)
            assert track is not None
            try:
                raw = mix.read_audio(ctx.settings.resolve_data_path(track.file_path))
                level = float(profile.get("music_level_db", -18.0))
                music_track = mix.loop_to(raw, n, sr) * mix.db_to_gain(level)
                duck = mix.merge_intervals(speech + narration_iv, gap=0.6)
                music_track *= mix.envelope(n, sr, duck, DUCK_MUSIC_UNDER_VOICE_DB, ramp=0.3)
                music_info.update(
                    status="added",
                    track_id=track.id,
                    title=track.title or Path(track.file_path).stem,
                    artist=track.artist,
                    license=track.license,
                    source_url=track.source_url,
                    mood=plan.music_mood or None,
                    level_db=level,
                    looped=bool(track.duration_seconds and track.duration_seconds < duration),
                )
                credits.append({"kind": "music", "text": _music_credit(track)})
            except (RuntimeError, ValueError) as exc:
                music_info["status"] = "error"
                notes.append(f"Musique « {track.title or track.file_path} » illisible : {exc}")

    # 4. Bruitages (Phase 7) : synthétisés, calés sur les effets et la transition d'entrée.
    sfx_info: dict[str, Any] = {"mode": profile.get("sfx_mode", "auto"), "status": "disabled"}
    sfx_track = np.zeros((2, n), dtype=np.float32)
    if sfx_info["mode"] == "auto":
        from app.audio.sfx import build_track

        events: list[tuple[float, str]] = []
        if profile.get("transition_in") == "zoom":
            events.append((0.3, "whoosh"))
        for e in plan.effects:
            events.append((e.t, "impact" if e.kind == "shake" else "whoosh"))
        if events:
            level = float(profile.get("sfx_level_db", -14.0))
            raw, placed = build_track(events, n, sr)
            sfx_track = raw * mix.db_to_gain(level)
            sfx_info.update(status="added", level_db=level, events=placed, synthetic=True)
        else:
            sfx_info["status"] = "none"

    # 5. Mixage ------------------------------------------------------------------------
    ctx.check_cancel()
    ctx.report_progress(0.85, "Mixage…")
    game = game * mix.db_to_gain(float(profile.get("game_level_db", 0.0)))
    if narration_iv:
        game = game * mix.envelope(n, sr, narration_iv, DUCK_GAME_UNDER_NARRATION_DB, ramp=0.2)
    final = (
        game
        + voice_track * mix.db_to_gain(float(profile.get("narration_level_db", 0.0)))
        + music_track
        + sfx_track
    )
    mix.write_wav(workdir / "audio_mix.wav", final)
    preview = workdir / "audio_preview.m4a"
    try:
        mix.encode_preview(workdir / "audio_mix.wav", preview)
    except RuntimeError as exc:
        notes.append(f"Aperçu audio non généré : {exc}")

    report = {
        "source_music": source_music,
        "narration": narration_info,
        "music": music_info,
        "sfx": sfx_info,
        "bleep": bleep_info,
        "levels": {
            "game_db": float(profile.get("game_level_db", 0.0)),
            "narration_db": float(profile.get("narration_level_db", 0.0)),
            "music_db": float(profile.get("music_level_db", -18.0)),
            "game_ducking_db": DUCK_GAME_UNDER_NARRATION_DB if narration_iv else 0.0,
        },
        "notes": notes,
    }
    with ctx.session_factory() as s:
        r = _render(ctx, s)
        r.audio_report_json = json.dumps(report, ensure_ascii=False)
        r.credits_json = json.dumps(credits, ensure_ascii=False)
        r.preview_audio_path = ctx.settings.to_relative(preview) if preview.is_file() else None
        s.commit()
    return {
        "source_music": source_music["status"],
        "attenuated": source_music["attenuated"],
        "narration": narration_info["status"],
        "narration_lines": len(narration_info["lines"]),
        "music": music_info["status"],
        "sfx": sfx_info["status"],
    }


# --------------------------------------------------------------------------- publication


def preparing_publication(ctx: StepContext) -> dict[str, Any]:
    """Textes prêts à copier pour TikTok et YouTube Shorts, avec les crédits obligatoires
    (ajoutés par le code, jamais laissés à l'IA) et la musique conseillée pour l'upload."""
    from app.services.publication import build_publication

    with ctx.session_factory() as s:
        r = _render(ctx, s)
        source = _source(ctx, s)
        plan = ed.EditorialPlan.model_validate_json(r.plan_json or "{}")
        profile = json.loads(r.profile_snapshot_json)
        cand = json.loads(r.candidate_snapshot_json) if r.candidate_snapshot_json else {}
        project_game = r.project_id and s.get(Project, r.project_id)
        pub = build_publication(
            plan=plan,
            source={
                "title": source.title,
                "uploader": source.uploader,
                "url": source.url,
                "rights_status": source.rights_status,
            },
            credits=json.loads(r.credits_json) if r.credits_json else [],
            candidate_summary=cand.get("summary"),
            game=project_game.game if project_game else None,
            censor=bool(profile.get("censor_profanity", True)),
            series=profile.get("series"),
            language=profile.get("output_language", "fr"),
        )
        r.publication_json = json.dumps(pub, ensure_ascii=False)
        s.commit()
    return {
        "youtube_title": pub["youtube"]["title"],
        "hashtags": pub["hashtags"],
        "music_suggestion": bool(pub["music_suggestion"]),
    }


# Ordre complet : l'audio précède les sous-titres (la narration placée y est sous-titrée).
RENDER_STEPS = {
    "creating_editorial_plan": creating_editorial_plan,
    "detecting_facecam": detecting_facecam,
    "preparing_audio": preparing_audio,
    "preparing_subtitles": preparing_subtitles,
    "rendering": rendering,
    "quality_check": quality_checking,
    "building_risk_report": building_risk_report,
    "preparing_publication": preparing_publication,
}
