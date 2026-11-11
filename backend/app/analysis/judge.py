"""Évaluation éditoriale d'un extrait candidat.

- ``AnthropicJudge`` : Claude (API) avec sortie structurée validée, images horodatées,
  budget vérifié avant l'appel, coût enregistré après (succès, refus ou erreur).
- ``signals_only_assessment`` : estimation locale sans IA, toujours signalée comme telle.

L'IA ne reçoit jamais la vidéo entière : seulement l'extrait de transcription, un résumé des
signaux et quelques images réduites. Elle ne peut rien exécuter : sa réponse est un JSON
validé, transformé en données par le code.
"""

from __future__ import annotations

import base64
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, Field, ValidationError

from app.core.config import Settings
from app.models import CRITERIA
from app.workers.errors import StepError

logger = logging.getLogger("app.analysis.judge")

FALLBACK_BETA = "server-side-fallback-2026-07-01"
MAX_OUTPUT_TOKENS = 8000
BOUNDS_TOLERANCE = 20.0


# --------------------------------------------------------------------------- schéma de sortie


class CriterionAssessment(BaseModel):
    score: int
    justification: str


class KeyEvent(BaseModel):
    t: float
    description: str


class ClipAssessment(BaseModel):
    """Réponse structurée demandée à l'IA (schéma imposé via output_format)."""

    summary: str
    reason: str
    hook: CriterionAssessment
    entertainment: CriterionAssessment
    standalone: CriterionAssessment
    narrative: CriterionAssessment
    retention: CriterionAssessment
    originality: CriterionAssessment
    av_quality: CriterionAssessment
    confidence: float
    key_events: list[KeyEvent]
    suggested_start: float
    suggested_end: float
    self_contained: bool
    warnings: list[str]


class _Bounded(BaseModel):
    """Contraintes vérifiées après coup (non garanties par le schéma)."""

    scores: dict[str, int] = Field(default_factory=dict)
    confidence: float = Field(ge=0, le=1)

    @classmethod
    def check(cls, a: ClipAssessment) -> None:
        bad = {k: getattr(a, k).score for k in CRITERIA if not 0 <= getattr(a, k).score <= 10}
        if bad:
            raise ValueError(f"Notes hors de l'échelle 0–10 : {bad}")
        cls(confidence=a.confidence)
        if not a.summary.strip() or not a.reason.strip():
            raise ValueError("Résumé ou raison vide")


# --------------------------------------------------------------------------- entrées / sorties


@dataclass
class JudgeContext:
    video_title: str | None
    creator: str | None
    game: str | None
    language: str
    profile_name: str
    editorial_focus: str | None
    min_duration: float
    max_duration: float
    video_duration: float


@dataclass
class JudgeInput:
    start: float
    end: float
    transcript: list[tuple[float, float, str]]  # (début, fin, texte) autour de l'extrait
    signals_summary: str
    frames: list[tuple[float, Path]]


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


@dataclass
class JudgeResult:
    status: str  # scored | refused | failed
    model: str
    assessment: ClipAssessment | None = None
    usage: Usage = field(default_factory=Usage)
    request_id: str | None = None
    error: str | None = None
    raw: str | None = None


BudgetCheck = Callable[[float], None]  # lève BudgetExceeded si l'appel risque de dépasser
UsageRecorder = Callable[[JudgeResult, int], None]  # (résultat, nb d'images) -> enregistrement


class ClipJudge(Protocol):
    model: str

    def judge(
        self,
        context: JudgeContext,
        item: JudgeInput,
        budget_check: BudgetCheck,
        record_usage: UsageRecorder,
    ) -> JudgeResult: ...


# --------------------------------------------------------------------------- prompt


def mmss(t: float) -> str:
    t = max(0, int(round(t)))
    return (
        f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}" if t >= 3600 else f"{t // 60}:{t % 60:02d}"
    )


def system_prompt(ctx: JudgeContext) -> str:
    criteria = "\n".join(f"- {key} : {label}" for key, label in CRITERIA.items())
    return f"""Tu es éditeur vidéo spécialisé dans les formats courts verticaux de jeux vidéo \
(TikTok, YouTube Shorts). Tu évalues UN extrait candidat d'une vidéo longue de gameplay, afin \
d'aider un créateur à décider s'il mérite d'être monté en short. Le créateur garde toujours la \
décision finale.

Vidéo source : « {ctx.video_title or "titre inconnu"} » — créateur : {ctx.creator or "inconnu"} — \
jeu : {ctx.game or "non précisé"} — durée totale : {mmss(ctx.video_duration)}.
Profil éditorial : {ctx.profile_name}.
Angle recherché : {ctx.editorial_focus or "moments forts, compréhensibles sans contexte."}

Éléments fournis pour chaque extrait : la transcription horodatée (verbatim, éventuellement dans \
une autre langue), un résumé de signaux mesurés automatiquement (énergie sonore, débit de parole, \
changements de scène) et quelques images réduites horodatées.

Règles impératives :
1. Appuie-toi uniquement sur ces éléments. N'invente aucun événement, dialogue, intention ou \
résultat qui n'est ni visible dans les images ni audible dans la transcription. Les signaux \
indiquent seulement qu'un son est plus fort que d'habitude, pas sa nature.
2. Le résumé est factuel. La raison explique pourquoi l'extrait pourrait (ou non) fonctionner \
en short, sans exagération.
3. Note chaque critère de 0 à 10 (entier) avec une justification d'une phrase :
{criteria}
   Ces notes sont des estimations éditoriales, jamais des prédictions de vues.
4. confidence (0 à 1) reflète la qualité des éléments disponibles : baisse-la si les images \
ou la transcription ne permettent pas de comprendre ce qui se passe, et explique pourquoi dans \
warnings.
5. key_events : les moments notables avec leur instant t en secondes (dans l'extrait).
6. Bornes : suggested_start et suggested_end peuvent ajuster l'extrait pour démarrer sur \
l'accroche et finir sur une chute, à {BOUNDS_TOLERANCE:.0f} s maximum des bornes proposées, avec \
une durée comprise entre {ctx.min_duration:.0f} et {ctx.max_duration:.0f} s. Sinon, renvoie \
exactement les bornes proposées.
7. self_contained : true seulement si l'extrait se comprend sans avoir vu le reste de la vidéo.
8. warnings : limites de l'analyse, risques (musique identifiable, contenu sensible, facecam \
visible, passage incompréhensible…). Liste vide s'il n'y en a pas.
9. Rédige summary, reason, justifications, descriptions d'événements et warnings en langue \
« {ctx.language} »."""


def user_content(item: JudgeInput) -> list[dict[str, object]]:
    lines = []
    for start, end, text in item.transcript:
        middle = (start + end) / 2  # lignes redécoupées aux bornes : le milieu tranche
        outside = middle < item.start or middle >= item.end
        tag = " (hors extrait)" if outside else ""
        lines.append(f"[{mmss(start)}–{mmss(end)}]{tag} {text}")
    transcript = "\n".join(lines) or "(aucune parole détectée dans cet intervalle)"
    content: list[dict[str, object]] = [
        {
            "type": "text",
            "text": (
                f"Extrait proposé : {mmss(item.start)} → {mmss(item.end)} "
                f"(start={item.start:.1f} s, end={item.end:.1f} s, "
                f"durée {item.end - item.start:.0f} s).\n\n"
                f"Transcription horodatée :\n{transcript}\n\n"
                f"Signaux mesurés : {item.signals_summary}\n\n"
                + (
                    f"{len(item.frames)} images horodatées suivent."
                    if item.frames
                    else "Aucune image fournie : n'évalue pas ce qui est visible."
                )
            ),
        }
    ]
    for t, path in item.frames:
        content.append({"type": "text", "text": f"Image à {mmss(t)} (t={t:.1f} s) :"})
        content.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": base64.standard_b64encode(path.read_bytes()).decode("ascii"),
                },
            }
        )
    return content


# --------------------------------------------------------------------------- Claude


class AnthropicJudge:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.model = settings.llm_model
        self._client = None

    @property
    def configured(self) -> bool:
        return self.settings.anthropic_api_key is not None

    def client(self):  # type: ignore[no-untyped-def]
        if self._client is None:
            import anthropic

            key = self.settings.anthropic_api_key
            self._client = anthropic.Anthropic(
                api_key=key.get_secret_value() if key else None, max_retries=3, timeout=300.0
            )
        return self._client

    def _cost(self, usage: Usage) -> float:
        from app.services.budget import cost_usd

        return cost_usd(
            self.settings,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_read_tokens=usage.cache_read_tokens,
            cache_write_tokens=usage.cache_write_tokens,
        )

    def judge(
        self,
        context: JudgeContext,
        item: JudgeInput,
        budget_check: BudgetCheck,
        record_usage: UsageRecorder,
    ) -> JudgeResult:
        import anthropic

        if not self.configured:
            raise StepError(
                "Clé API absente : ajoutez ANTHROPIC_API_KEY dans le fichier .env, "
                "ou lancez l'analyse en mode « signaux seuls »."
            )
        client = self.client()
        system = [
            {
                "type": "text",
                "text": system_prompt(context),
                "cache_control": {"type": "ephemeral"},  # identique pour tous les extraits
            }
        ]
        messages = [{"role": "user", "content": user_content(item)}]
        try:
            counted = client.messages.count_tokens(
                model=self.model, system=system, messages=messages
            ).input_tokens
        except anthropic.APIError as exc:
            raise StepError(f"Comptage des jetons impossible : {exc}", technical=repr(exc)) from exc
        # Estimation haute : schéma (~600 jetons) + sortie maximale.
        estimate = self._cost(Usage(input_tokens=counted + 600, output_tokens=MAX_OUTPUT_TOKENS))
        budget_check(estimate)

        attempts = 0
        repair_note: str | None = None
        while True:
            attempts += 1
            msgs = messages
            if repair_note:  # une seule relance, avec la raison du rejet
                note = {
                    "type": "text",
                    "text": f"Une réponse précédente était invalide ({repair_note}). "
                    "Respecte strictement les règles.",
                }
                msgs = [{"role": "user", "content": [*user_content(item), note]}]
            try:
                response = client.beta.messages.parse(
                    model=self.model,
                    max_tokens=MAX_OUTPUT_TOKENS,
                    system=system,
                    messages=msgs,
                    output_format=ClipAssessment,
                    output_config={"effort": self.settings.llm_effort},
                    betas=[FALLBACK_BETA],
                    fallbacks="default",
                )
            except anthropic.AuthenticationError as exc:
                raise StepError(
                    "Clé API refusée par Anthropic (vérifiez ANTHROPIC_API_KEY)."
                ) from exc
            except anthropic.PermissionDeniedError as exc:
                raise StepError("Accès refusé par l'API Anthropic pour ce modèle.") from exc
            except anthropic.RateLimitError as exc:
                raise StepError("Limite de débit de l'API atteinte : relancez plus tard.") from exc
            except anthropic.APIConnectionError as exc:
                raise StepError("Connexion à l'API Anthropic impossible.") from exc
            except anthropic.APIStatusError as exc:
                raise StepError(
                    f"Erreur de l'API Anthropic ({exc.status_code}).", technical=str(exc)
                ) from exc

            u = response.usage
            usage = Usage(
                input_tokens=u.input_tokens or 0,
                output_tokens=u.output_tokens or 0,
                cache_read_tokens=getattr(u, "cache_read_input_tokens", 0) or 0,
                cache_write_tokens=getattr(u, "cache_creation_input_tokens", 0) or 0,
            )
            request_id = getattr(response, "_request_id", None)
            model = getattr(response, "model", self.model) or self.model

            if response.stop_reason == "refusal":
                category = getattr(getattr(response, "stop_details", None), "category", None)
                result = JudgeResult(
                    "refused",
                    model,
                    usage=usage,
                    request_id=request_id,
                    error=f"L'IA a refusé d'évaluer cet extrait ({category}).",
                )
                record_usage(result, len(item.frames))
                return result
            if response.stop_reason == "max_tokens":
                result = JudgeResult(
                    "failed",
                    model,
                    usage=usage,
                    request_id=request_id,
                    error="Réponse tronquée (limite de jetons).",
                )
                record_usage(result, len(item.frames))
                return result

            assessment = response.parsed_output
            raw = assessment.model_dump_json() if assessment else None
            try:
                if assessment is None:
                    raise ValueError("aucune sortie structurée")
                _Bounded.check(assessment)
            except (ValueError, ValidationError) as exc:
                result = JudgeResult(
                    "failed",
                    model,
                    usage=usage,
                    request_id=request_id,
                    error=f"Réponse invalide : {exc}",
                    raw=raw,
                )
                record_usage(result, len(item.frames))
                if attempts >= 2:
                    return result
                repair_note = str(exc)[:300]
                budget_check(estimate)
                continue
            result = JudgeResult(
                "scored", model, assessment=assessment, usage=usage, request_id=request_id, raw=raw
            )
            record_usage(result, len(item.frames))
            return result


# --------------------------------------------------------------------------- sans IA


def signals_only_assessment(
    *,
    start: float,
    end: float,
    interest: list[float],
    excitement: list[float],
    speech_rate: list[float],
    scene_density: list[float],
    boundary_on_sentence: tuple[bool, bool],
    first_line: str | None,
    av_score: float,
    language: str,
) -> ClipAssessment:
    """Estimation grossière à partir des signaux. Explications générées, confiance basse."""
    a, b = int(start), max(int(end), int(start) + 1)

    def m(xs: list[float], i: int, j: int) -> float:
        seg = xs[i:j]
        return float(sum(seg) / len(seg)) if seg else 0.0

    def mx(xs: list[float], i: int, j: int) -> float:
        seg = xs[i:j]
        return float(max(seg)) if seg else 0.0

    s = lambda x: max(0, min(10, round(x * 10)))  # noqa: E731
    speech_cov = sum(1 for x in speech_rate[a:b] if x > 0) / max(b - a, 1)
    hook = s(0.6 * mx(interest, a, a + 10) + 0.4 * m(interest, a, a + 10))
    ent = s(0.5 * mx(excitement, a, b) + 0.5 * m(interest, a, b))
    standalone = s(0.3 + 0.35 * sum(boundary_on_sentence) / 2 + 0.35 * min(speech_cov * 1.5, 1))
    narrative = s(min(speech_cov * 1.2, 1) * 0.8)
    retention = s(m(interest, a, b) * 0.7 + mx(scene_density, a, b) * 0.3)
    cuts = sum(1 for x in scene_density[a:b] if x > 0.15)
    peaks = [i for i in range(a, min(b, len(excitement))) if excitement[i] >= 0.66]
    j = "Estimation par signaux (sans IA)."

    def ca(score: int, text: str) -> CriterionAssessment:
        return CriterionAssessment(score=score, justification=f"{j} {text}")

    return ClipAssessment(
        summary=(
            f"Extrait de {end - start:.0f} s. Début : « {first_line[:160]} »"
            if first_line
            else f"Extrait de {end - start:.0f} s sans parole détectée."
        ),
        reason=(
            f"Proposé par les signaux : {len(peaks)} pic(s) sonore(s), "
            f"parole sur {speech_cov:.0%} de la durée, activité de montage "
            f"{'élevée' if cuts > (b - a) / 10 else 'modérée'}."
        ),
        hook=ca(hook, "Intérêt mesuré dans les 10 premières secondes."),
        entertainment=ca(ent, "Pics d'énergie sonore et intérêt moyen."),
        standalone=ca(standalone, "Bornes calées sur des phrases et présence de parole."),
        narrative=ca(narrative, "Part de l'extrait avec de la parole."),
        retention=ca(retention, "Intérêt moyen et rythme des changements de scène."),
        originality=ca(5, "Non estimable sans IA : valeur neutre."),
        av_quality=ca(round(av_score), "Résolution et cadence de la source."),
        confidence=0.25,
        key_events=[KeyEvent(t=float(i), description="Pic sonore") for i in peaks[:5]],
        suggested_start=start,
        suggested_end=end,
        self_contained=all(boundary_on_sentence),
        warnings=[
            "Évaluation sans IA : notes approximatives fondées uniquement sur des signaux "
            "audio, de parole et de montage. Le contenu réel n'a pas été compris."
        ],
    )


def parse_raw(raw: str | None) -> dict[str, object] | None:
    return json.loads(raw) if raw else None
