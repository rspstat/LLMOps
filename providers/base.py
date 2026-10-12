from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: str
    content: str


@dataclass(frozen=True, slots=True)
class ProviderRequest:
    messages: tuple[ChatMessage, ...]
    max_tokens: int
    temperature: float | None = None


@dataclass(frozen=True, slots=True)
class ProviderResponse:
    content: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    finish_reason: str = "stop"


class ProviderError(Exception):
    """Any failure to obtain a completion (network, HTTP status, malformed payload)."""


@runtime_checkable
class Provider(Protocol):
    """Common interface every model backend (mock, SLM, frontier API, Jev) implements.

    Latency is measured by the caller, so each attempt, including fallbacks, is timed the same way.
    """

    name: str

    async def complete(self, request: ProviderRequest) -> ProviderResponse: ...
