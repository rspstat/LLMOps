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
