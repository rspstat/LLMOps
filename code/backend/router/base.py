from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol


class Route(StrEnum):
    SMALL = "small"
    FRONTIER = "frontier"


@dataclass(frozen=True, slots=True)
class JudgeRecord:
    """What one call to the decision provider cost and returned, for the `judge` trace event."""

    provider: str
    latency_ms: int
    policy_version: str
    choice: str | None = None
    probabilities: Mapping[str, float] | None = None
    confidence: float | None = None
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass(frozen=True, slots=True)
class RouteDecision:
    route: Route
    reason: str
    # 1.0 when an explicit rule fired; lower when the route is only a default. For judged
    # decisions it is the judge's probability that the request is "easy".
    confidence: float
    judge: JudgeRecord | None = None
    detail: Mapping[str, Any] = field(default_factory=dict)


class Router(Protocol):
    async def route(self, text: str) -> RouteDecision: ...
