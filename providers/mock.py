from providers.base import ProviderError, ProviderRequest, ProviderResponse

_CHARS_PER_TOKEN = 4
_ECHO_LIMIT = 80


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // _CHARS_PER_TOKEN)


class MockProvider:
    """Deterministic offline provider: echoes the last user message. Never touches the network.

    Pass `fail=True` to simulate an outage, which exercises the fallback path.
    """

    def __init__(self, name: str = "mock", *, fail: bool = False) -> None:
        self.name = name
        self.fail = fail
        self.calls = 0

    async def complete(self, request: ProviderRequest) -> ProviderResponse:
        self.calls += 1
        if self.fail:
            raise ProviderError(f"{self.name}: simulated outage")

        last_user = next((m.content for m in reversed(request.messages) if m.role == "user"), "")
        content = f"[{self.name}] {last_user[:_ECHO_LIMIT]}"
        completion_tokens = estimate_tokens(content)
        finish_reason = "stop"
        if completion_tokens > request.max_tokens:
            content = content[: request.max_tokens * _CHARS_PER_TOKEN]
            completion_tokens = request.max_tokens
            finish_reason = "length"

        return ProviderResponse(
            content=content,
            model=self.name,
            prompt_tokens=sum(estimate_tokens(m.content) for m in request.messages),
            completion_tokens=completion_tokens,
            finish_reason=finish_reason,
        )
