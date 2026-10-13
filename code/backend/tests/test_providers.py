import pytest

from providers.base import ChatMessage, Provider, ProviderError, ProviderRequest
from providers.mock import MockProvider


def make_request(text: str = "hello world", max_tokens: int = 100) -> ProviderRequest:
    return ProviderRequest(messages=(ChatMessage("user", text),), max_tokens=max_tokens)


def test_mock_provider_satisfies_provider_protocol():
    assert isinstance(MockProvider(), Provider)


@pytest.mark.anyio
async def test_mock_echoes_last_user_message_deterministically():
    provider = MockProvider("small")
    request = ProviderRequest(
        messages=(
            ChatMessage("system", "be brief"),
            ChatMessage("user", "first"),
            ChatMessage("assistant", "ok"),
            ChatMessage("user", "second"),
        ),
        max_tokens=100,
    )
    first = await provider.complete(request)
    second = await provider.complete(request)
    assert first == second
    assert first.content == "[small] second"
    assert first.model == "small"
    assert first.prompt_tokens > 0 and first.completion_tokens > 0
    assert first.finish_reason == "stop"
    assert provider.calls == 2


@pytest.mark.anyio
async def test_mock_respects_max_tokens():
    response = await MockProvider().complete(make_request("x" * 500, max_tokens=3))
    assert response.completion_tokens == 3
    assert response.finish_reason == "length"
    assert len(response.content) <= 3 * 4


@pytest.mark.anyio
async def test_failing_mock_raises_provider_error():
    with pytest.raises(ProviderError):
        await MockProvider("down", fail=True).complete(make_request())
