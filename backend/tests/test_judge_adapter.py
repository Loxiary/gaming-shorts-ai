"""AnthropicJudge avec un client simulé : aucun appel réseau, aucun coût."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from app.analysis.judge import (
    FALLBACK_BETA,
    AnthropicJudge,
    ClipAssessment,
    CriterionAssessment,
    JudgeContext,
    JudgeInput,
    system_prompt,
    user_content,
)
from app.core.config import Settings
from app.services.budget import BudgetExceeded
from app.workers.errors import StepError


def _assessment(score: int = 7, confidence: float = 0.7) -> ClipAssessment:
    c = CriterionAssessment(score=score, justification="ok")
    return ClipAssessment(
        summary="Le joueur saute du pont.",
        reason="Cascade spectaculaire.",
        hook=c,
        entertainment=c,
        standalone=c,
        narrative=c,
        retention=c,
        originality=c,
        av_quality=c,
        confidence=confidence,
        key_events=[],
        suggested_start=10,
        suggested_end=90,
        self_contained=True,
        warnings=[],
    )


def _response(parsed, stop_reason="end_turn"):  # type: ignore[no-untyped-def]
    usage = SimpleNamespace(
        input_tokens=3000,
        output_tokens=800,
        cache_read_input_tokens=1200,
        cache_creation_input_tokens=0,
    )
    return SimpleNamespace(
        parsed_output=parsed,
        stop_reason=stop_reason,
        usage=usage,
        model="claude-sonnet-5-5",
        _request_id="req_test",
        stop_details=SimpleNamespace(category="general_harms"),
    )


class _Client:
    def __init__(self, responses: list) -> None:  # type: ignore[type-arg]
        self.responses = responses
        self.parse_calls: list[dict] = []  # type: ignore[type-arg]
        self.messages = SimpleNamespace(
            count_tokens=lambda **kw: SimpleNamespace(input_tokens=4000)
        )
        self.beta = SimpleNamespace(messages=SimpleNamespace(parse=self._parse))

    def _parse(self, **kwargs):  # type: ignore[no-untyped-def]
        self.parse_calls.append(kwargs)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture
def judge(settings: Settings) -> AnthropicJudge:
    settings.anthropic_api_key = SecretStr("sk-ant-test")
    return AnthropicJudge(settings)


CTX = JudgeContext(
    video_title="Partie",
    creator="Moi",
    game="GTA 6",
    language="fr",
    profile_name="Viral",
    editorial_focus="Humour",
    min_duration=61,
    max_duration=180,
    video_duration=600,
)


def _input(tmp_path: Path) -> JudgeInput:
    frame = tmp_path / "f.jpg"
    frame.write_bytes(b"\xff\xd8\xff\xe0fakejpeg")
    return JudgeInput(
        start=10,
        end=90,
        transcript=[(5, 9, "Avant"), (12, 15, "Regarde ça !")],
        signals_summary="pics à 20 s",
        frames=[(20.0, frame)],
    )


def test_prompt_contains_rules_and_evidence(tmp_path: Path) -> None:
    text = system_prompt(CTX)
    assert "N'invente aucun événement" in text and "jamais des prédictions de vues" in text
    assert "61" in text and "180" in text and "« fr »" in text and "Humour" in text
    content = user_content(_input(tmp_path))
    assert "(hors extrait) Avant" in content[0]["text"]
    assert content[1]["text"].startswith("Image à 0:20")
    assert content[2]["type"] == "image" and content[2]["source"]["media_type"] == "image/jpeg"


def test_scored_call_records_usage_and_uses_safe_options(
    judge: AnthropicJudge, tmp_path: Path
) -> None:
    client = _Client([_response(_assessment())])
    judge._client = client
    estimates: list[float] = []
    recorded: list = []  # type: ignore[type-arg]
    result = judge.judge(
        CTX, _input(tmp_path), estimates.append, lambda r, n: recorded.append((r, n))
    )
    assert result.status == "scored" and result.assessment and result.request_id == "req_test"
    assert estimates and estimates[0] > 0  # budget vérifié AVANT l'appel
    assert recorded[0][1] == 1 and recorded[0][0].usage.cache_read_tokens == 1200
    call = client.parse_calls[0]
    assert call["model"] == "claude-sonnet-5-5"
    assert call["output_format"] is ClipAssessment
    assert call["output_config"] == {"effort": "medium"}
    assert call["betas"] == [FALLBACK_BETA] and call["fallbacks"] == "default"
    assert call["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert "thinking" not in call and "temperature" not in call


def test_budget_refusal_prevents_any_call(judge: AnthropicJudge, tmp_path: Path) -> None:
    client = _Client([_response(_assessment())])
    judge._client = client

    def deny(_estimate: float) -> None:
        raise BudgetExceeded("Plafond mensuel atteint")

    with pytest.raises(BudgetExceeded):
        judge.judge(CTX, _input(tmp_path), deny, lambda *_: None)
    assert client.parse_calls == []


def test_refusal_is_reported(judge: AnthropicJudge, tmp_path: Path) -> None:
    judge._client = _Client([_response(None, stop_reason="refusal")])
    recorded: list = []  # type: ignore[type-arg]
    result = judge.judge(CTX, _input(tmp_path), lambda _e: None, lambda r, n: recorded.append(r))
    assert result.status == "refused" and "general_harms" in result.error
    assert recorded and recorded[0].status == "refused"


def test_invalid_answer_is_retried_once_then_fails(judge: AnthropicJudge, tmp_path: Path) -> None:
    bad = _assessment(score=14)
    client = _Client([_response(bad), _response(_assessment(confidence=3))])
    judge._client = client
    recorded: list = []  # type: ignore[type-arg]
    result = judge.judge(CTX, _input(tmp_path), lambda _e: None, lambda r, n: recorded.append(r))
    assert result.status == "failed" and "invalide" in result.error
    assert len(client.parse_calls) == 2 and len(recorded) == 2  # chaque appel est facturé
    note = client.parse_calls[1]["messages"][0]["content"][-1]["text"]
    assert "invalide" in note


def test_repair_succeeds(judge: AnthropicJudge, tmp_path: Path) -> None:
    judge._client = _Client([_response(_assessment(score=-1)), _response(_assessment())])
    result = judge.judge(CTX, _input(tmp_path), lambda _e: None, lambda *_: None)
    assert result.status == "scored"


def test_missing_key_and_auth_errors(settings: Settings, tmp_path: Path) -> None:
    import anthropic
    import httpx2

    no_key = AnthropicJudge(settings)
    with pytest.raises(StepError, match="Clé API absente"):
        no_key.judge(CTX, _input(tmp_path), lambda _e: None, lambda *_: None)

    settings.anthropic_api_key = SecretStr("sk-ant-mauvaise")
    judge = AnthropicJudge(settings)
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    err = anthropic.AuthenticationError(
        "invalid x-api-key", response=httpx2.Response(401, request=request), body=None
    )
    judge._client = _Client([err])
    with pytest.raises(StepError, match="Clé API refusée"):
        judge.judge(CTX, _input(tmp_path), lambda _e: None, lambda *_: None)
