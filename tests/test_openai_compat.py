import json

import httpx
import pytest

from providers.base import ChatMessage, Provider, ProviderError, ProviderRequest
from providers.openai_compat import OpenAICompatProvider

REQUEST = ProviderRequest(
    messages=(ChatMessage("system", "be brief"), ChatMessage("user", "hi there")),
    max_tokens=16,
    temperature=0.2,
)

OK_BODY = {
    "model": "served-model",
    "choices": [{"message": {"role": "assistant", "content": "hello"}, "finish_reason": "stop"}],
    "usage": {"prompt_tokens": 7, "completion_tokens": 2},
}


def make_provider(handler, **kwargs) -> OpenAICompatProvider:
    options = {"base_url": "http://slm.test/v1", "model": "tiny", "api_key": "secret-key-123"}
    options.update(kwargs)
    return OpenAICompatProvider("slm", transport=httpx.MockTransport(handler), **options)


def test_satisfies_provider_protocol():
    assert isinstance(make_provider(lambda r: httpx.Response(200, json=OK_BODY)), Provider)


@pytest.mark.anyio
async def test_sends_openai_style_request_and_parses_response():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=OK_BODY)

    response = await make_provider(handler, base_url="http://slm.test/v1/").complete(REQUEST)

    assert seen["url"] == "http://slm.test/v1/chat/completions"
    assert seen["auth"] == "Bearer secret-key-123"
    assert seen["body"] == {
        "model": "tiny",
        "messages": [
            {"role": "system", "content": "be brief"},
            {"role": "user", "content": "hi there"},
        ],
        "max_tokens": 16,
        "temperature": 0.2,
    }
    assert response.content == "hello"
    assert response.model == "served-model"
    assert (response.prompt_tokens, response.completion_tokens) == (7, 2)
    assert response.finish_reason == "stop"


@pytest.mark.anyio
async def test_omits_auth_header_and_temperature_when_unset():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["headers"] = request.headers
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=OK_BODY)

    bare = ProviderRequest(messages=(ChatMessage("user", "hi"),), max_tokens=8)
    await make_provider(handler, api_key=None).complete(bare)
    assert "authorization" not in seen["headers"]
    assert "temperature" not in seen["body"]


@pytest.mark.anyio
async def test_missing_usage_falls_back_to_estimates():
    body = {"choices": [{"message": {"content": "abcdefgh"}}]}
    response = await make_provider(lambda r: httpx.Response(200, json=body)).complete(REQUEST)
    assert response.prompt_tokens > 0
    assert response.completion_tokens == 2
    assert response.model == "tiny"


@pytest.mark.anyio
async def test_http_error_raises_provider_error_without_leaking_key():
    handler = lambda r: httpx.Response(401, text="bad credentials")  # noqa: E731
    with pytest.raises(ProviderError) as info:
        await make_provider(handler).complete(REQUEST)
    assert "401" in str(info.value)
    assert "secret-key-123" not in str(info.value)


@pytest.mark.anyio
async def test_timeout_raises_provider_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(ProviderError, match="ReadTimeout"):
        await make_provider(handler).complete(REQUEST)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="not json"),
        httpx.Response(200, json={"choices": []}),
        httpx.Response(200, json={"choices": [{"message": {"content": None}}]}),
        httpx.Response(200, json=["unexpected"]),
    ],
)
async def test_malformed_payload_raises_provider_error(response):
    with pytest.raises(ProviderError, match="malformed"):
        await make_provider(lambda r: response).complete(REQUEST)


MAX_TOKENS_REJECTED = (
    "Unsupported parameter: 'max_tokens' is not supported with this model. "
    "Use 'max_completion_tokens' instead."
)
TEMPERATURE_REJECTED = (
    "Unsupported value: 'temperature' does not support 0.2 with this model. "
    "Only the default (1) value is supported."
)


def rejecting(messages: list[str], log: list[dict]):
    """Answer the first requests with the given 400 messages, then succeed; log every body."""
    queue = list(messages)

    def handler(request: httpx.Request) -> httpx.Response:
        log.append(json.loads(request.content))
        if queue:
            return httpx.Response(400, json={"error": {"message": queue.pop(0)}})
        return httpx.Response(200, json=OK_BODY)

    return handler


@pytest.mark.anyio
async def test_resends_with_max_completion_tokens_when_the_server_asks_and_remembers_it():
    bodies: list[dict] = []
    provider = make_provider(rejecting([MAX_TOKENS_REJECTED], bodies))

    assert (await provider.complete(REQUEST)).content == "hello"
    assert "max_tokens" in bodies[0] and "max_completion_tokens" not in bodies[0]
    assert bodies[1]["max_completion_tokens"] == 16 and "max_tokens" not in bodies[1]

    await provider.complete(REQUEST)
    assert len(bodies) == 3 and "max_completion_tokens" in bodies[2]  # no further probing


@pytest.mark.anyio
async def test_resends_without_temperature_when_the_server_rejects_it_and_remembers_it():
    bodies: list[dict] = []
    provider = make_provider(rejecting([TEMPERATURE_REJECTED], bodies))

    await provider.complete(REQUEST)
    assert bodies[0]["temperature"] == 0.2 and "temperature" not in bodies[1]
    assert bodies[1]["max_tokens"] == 16  # only the named parameter changed

    await provider.complete(REQUEST)
    assert len(bodies) == 3 and "temperature" not in bodies[2]


@pytest.mark.anyio
async def test_adapts_to_both_problems_in_turn():
    bodies: list[dict] = []
    provider = make_provider(rejecting([MAX_TOKENS_REJECTED, TEMPERATURE_REJECTED], bodies))
    assert (await provider.complete(REQUEST)).content == "hello"
    assert len(bodies) == 3
    assert "max_completion_tokens" in bodies[2] and "temperature" not in bodies[2]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("status", "text"),
    [
        (400, "Invalid model name"),  # a 400 that names neither parameter
        (401, "max_completion_tokens temperature"),  # right words, wrong status
        (429, "max_completion_tokens temperature"),
        (500, "max_completion_tokens temperature"),
    ],
)
async def test_other_errors_are_never_resent(status, text):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(status, text=text)

    with pytest.raises(ProviderError, match=f"HTTP {status}"):
        await make_provider(handler).complete(REQUEST)
    assert len(calls) == 1


@pytest.mark.anyio
async def test_a_server_that_keeps_complaining_is_given_up_on():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(400, text=MAX_TOKENS_REJECTED)

    with pytest.raises(ProviderError, match="HTTP 400"):
        await make_provider(handler).complete(REQUEST)
    assert len(calls) == 2  # original + one resend; the same complaint again changes nothing


@pytest.mark.anyio
async def test_no_temperature_is_never_added_or_asked_about():
    bodies: list[dict] = []
    bare = ProviderRequest(messages=(ChatMessage("user", "hi"),), max_tokens=8)
    await make_provider(rejecting([], bodies)).complete(bare)
    assert "temperature" not in bodies[0]


@pytest.mark.anyio
async def test_a_budget_spent_on_hidden_reasoning_is_an_empty_answer_not_a_malformed_one():
    empty = {"choices": [{"message": {"content": None}, "finish_reason": "length"}], "usage": {}}
    response = await make_provider(lambda r: httpx.Response(200, json=empty)).complete(REQUEST)
    assert response.content == "" and response.finish_reason == "length"
