import json

import httpx
import pytest

from providers.base import ProviderError
from providers.decision import ChoiceQuestion, DecisionProvider
from providers.jev import JevProvider

URL = "https://api.typesafe.ai/v1/systemone"
SECRET = "jev-secret-key-123"
QUESTION = ChoiceQuestion(
    "difficulty", "How hard is it?", {"easy": "simple lookups", "hard": "multi-step reasoning"}
)

OK_BODY = {
    "model": "jev-1.13.0",
    "answers": {
        "difficulty": {
            "type": "choice",
            "choice": "easy",
            "probabilities": {"easy": 0.82, "hard": 0.18},
            "confidence": 0.91,
        }
    },
    "usage": {"input_tokens": 120, "output_tokens": 3},
}


def make_provider(handler, **kwargs) -> JevProvider:
    options = {"url": URL, "model": "jev-latest", "api_key": SECRET} | kwargs
    return JevProvider(transport=httpx.MockTransport(handler), **options)


def body_with(**answer_overrides) -> dict:
    answer = OK_BODY["answers"]["difficulty"] | answer_overrides
    return OK_BODY | {"answers": {"difficulty": answer}}


def test_satisfies_decision_provider_protocol():
    assert isinstance(make_provider(lambda r: httpx.Response(200, json=OK_BODY)), DecisionProvider)


@pytest.mark.anyio
async def test_sends_state_and_typed_question_and_parses_the_answer():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=OK_BODY)

    decision = await make_provider(handler).decide("POLICY + REQUEST", QUESTION)

    assert seen["url"] == URL  # used verbatim: no path appended
    assert seen["auth"] == f"Bearer {SECRET}"
    assert seen["body"] == {
        "model": "jev-latest",
        "state": "POLICY + REQUEST",
        "questions": {
            "difficulty": {
                "type": "choice",
                "instructions": "How hard is it?",
                "criteria": {"easy": "simple lookups", "hard": "multi-step reasoning"},
            }
        },
    }
    assert decision.choice == "easy"
    assert decision.probabilities == {"easy": 0.82, "hard": 0.18}
    assert decision.confidence == 0.91
    assert decision.model == "jev-1.13.0"
    assert (decision.input_tokens, decision.output_tokens) == (120, 3)


@pytest.mark.anyio
async def test_missing_confidence_falls_back_to_chosen_probability_and_usage_is_estimated():
    answer = {"type": "choice", "choice": "hard", "probabilities": {"easy": 0.3, "hard": 0.7}}
    body = {"answers": {"difficulty": answer}}
    decision = await make_provider(lambda r: httpx.Response(200, json=body)).decide(
        "x" * 40, QUESTION
    )
    assert decision.confidence == 0.7
    assert decision.input_tokens == 10 and decision.output_tokens == 1
    assert decision.model == "jev-latest"


@pytest.mark.anyio
async def test_http_error_raises_without_leaking_the_key():
    handler = lambda r: httpx.Response(403, text="not available for your tier")  # noqa: E731
    with pytest.raises(ProviderError) as info:
        await make_provider(handler).decide("s", QUESTION)
    assert "403" in str(info.value) and SECRET not in str(info.value)


@pytest.mark.anyio
async def test_timeout_raises_provider_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(ProviderError, match="ReadTimeout"):
        await make_provider(handler).decide("s", QUESTION)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="not json"),
        httpx.Response(200, json=["unexpected"]),
        httpx.Response(200, json={"answers": {}}),
        httpx.Response(200, json={"answers": {"other": OK_BODY["answers"]["difficulty"]}}),
        httpx.Response(200, json=body_with(type="score")),
        httpx.Response(200, json=body_with(choice=None)),
        httpx.Response(200, json=body_with(probabilities=[0.5, 0.5])),
        httpx.Response(200, json=body_with(confidence="high", probabilities={"hard": 0.1})),
    ],
)
async def test_malformed_payload_raises_provider_error(response):
    with pytest.raises(ProviderError):
        await make_provider(lambda r: response).decide("s", QUESTION)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, json=body_with(choice="medium")),
        httpx.Response(200, json=body_with(probabilities={"easy": 0.5, "other": 0.5})),
        httpx.Response(200, json=body_with(probabilities={"easy": 1.4, "hard": 0.0})),
        httpx.Response(200, json=body_with(probabilities={"easy": 0.9, "hard": 0.9})),
    ],
)
async def test_answers_that_do_not_fit_the_question_are_rejected(response):
    with pytest.raises(ProviderError, match="decision:"):
        await make_provider(lambda r: response).decide("s", QUESTION)
