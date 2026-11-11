"""Appel générique à Claude avec sortie structurée validée (plan éditorial, traduction).

Mêmes garde-fous que le juge des extraits : budget vérifié AVANT l'appel (jetons comptés +
sortie maximale), coût enregistré après chaque appel (succès, refus ou échec), une seule
relance si la réponse est invalide, erreurs API traduites en messages compréhensibles.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ValidationError

from app.analysis.judge import FALLBACK_BETA, Usage, api_error_message
from app.core.config import Settings
from app.workers.errors import StepError

T = TypeVar("T", bound=BaseModel)


@dataclass
class LLMResult(Generic[T]):  # noqa: UP046 (lisibilité, Python 3.12+)
    status: str  # ok | refused | failed
    model: str
    parsed: T | None = None
    usage: Usage = field(default_factory=Usage)
    request_id: str | None = None
    error: str | None = None


BudgetCheck = Callable[[float], None]
Recorder = Callable[[LLMResult[Any]], None]


class StructuredLLM:
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

    def cost(self, usage: Usage) -> float:
        from app.services.budget import cost_usd

        return cost_usd(
            self.settings,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_read_tokens=usage.cache_read_tokens,
            cache_write_tokens=usage.cache_write_tokens,
        )

    def call(
        self,
        *,
        system: str,
        content: list[dict[str, Any]],
        schema: type[T],
        budget_check: BudgetCheck,
        record: Recorder,
        validate: Callable[[T], None] | None = None,
        max_tokens: int = 8000,
    ) -> LLMResult[T]:
        import anthropic

        if not self.configured:
            raise StepError("Clé API absente : ajoutez ANTHROPIC_API_KEY dans le fichier .env.")
        client = self.client()
        system_blocks = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
        messages = [{"role": "user", "content": content}]
        try:
            counted = client.messages.count_tokens(
                model=self.model, system=system_blocks, messages=messages
            ).input_tokens
        except anthropic.APIError as exc:
            raise StepError(
                api_error_message(exc, "Comptage des jetons impossible"), technical=repr(exc)
            ) from exc
        estimate = self.cost(Usage(input_tokens=counted + 600, output_tokens=max_tokens))

        note: str | None = None
        for attempt in (1, 2):
            budget_check(estimate)
            msgs = messages
            if note:
                msgs = [
                    {
                        "role": "user",
                        "content": [
                            *content,
                            {
                                "type": "text",
                                "text": f"Une réponse précédente était invalide ({note}). "
                                "Respecte strictement les consignes.",
                            },
                        ],
                    }
                ]
            try:
                response = client.beta.messages.parse(
                    model=self.model,
                    max_tokens=max_tokens,
                    system=system_blocks,
                    messages=msgs,
                    output_format=schema,
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
                    api_error_message(exc, "Appel à l'IA impossible"), technical=str(exc)
                ) from exc

            u = response.usage
            usage = Usage(
                input_tokens=u.input_tokens or 0,
                output_tokens=u.output_tokens or 0,
                cache_read_tokens=getattr(u, "cache_read_input_tokens", 0) or 0,
                cache_write_tokens=getattr(u, "cache_creation_input_tokens", 0) or 0,
            )
            model = getattr(response, "model", self.model) or self.model
            request_id = getattr(response, "_request_id", None)
            if response.stop_reason == "refusal":
                result: LLMResult[T] = LLMResult(
                    "refused",
                    model,
                    usage=usage,
                    request_id=request_id,
                    error="L'IA a refusé cette demande.",
                )
                record(result)
                return result
            parsed = response.parsed_output
            try:
                if response.stop_reason == "max_tokens" or parsed is None:
                    raise ValueError("réponse incomplète")
                if validate:
                    validate(parsed)
            except (ValueError, ValidationError) as exc:
                result = LLMResult(
                    "failed",
                    model,
                    usage=usage,
                    request_id=request_id,
                    error=f"Réponse invalide : {exc}",
                )
                record(result)
                if attempt == 2:
                    return result
                note = str(exc)[:300]
                continue
            result = LLMResult("ok", model, parsed=parsed, usage=usage, request_id=request_id)
            record(result)
            return result
        raise AssertionError("unreachable")
