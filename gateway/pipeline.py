import hashlib
import time
from collections.abc import Sequence
from dataclasses import dataclass

from gateway.trace import TraceRecorder
from guards.base import GuardResult
from guards.input_guard import InputGuard
from providers.base import (
    ChatMessage,
    Provider,
    ProviderError,
    ProviderRequest,
    ProviderResponse,
)
from providers.registry import ProviderRegistry
from router.rule_router import RouteDecision, RuleRouter


class ProviderUnavailableError(Exception):
    """The routed provider and the fallback both failed."""


@dataclass(frozen=True, slots=True)
class Price:
    """USD per 1M tokens."""

    input_per_mtok: float = 0.0
    output_per_mtok: float = 0.0

    def cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        total = prompt_tokens * self.input_per_mtok + completion_tokens * self.output_per_mtok
        return total / 1_000_000


@dataclass(frozen=True, slots=True)
class Blocked:
    guard: GuardResult


@dataclass(frozen=True, slots=True)
class Completed:
    response: ProviderResponse
    route: RouteDecision
    provider: str
    fallback_used: bool


def _elapsed_ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


class Pipeline:
    """Input guard -> router -> provider (with fallback), recording one trace event per stage."""

    def __init__(
        self,
        *,
        guard: InputGuard,
        router: RuleRouter,
        providers: ProviderRegistry,
        prices: dict[str, Price],
        max_output_tokens: int,
        store_content: bool = False,
    ) -> None:
        self._guard = guard
        self._router = router
        self._providers = providers
        self._prices = prices
        self._max_output_tokens = max_output_tokens
        self._store_content = store_content

    async def run(
        self,
        recorder: TraceRecorder,
        messages: Sequence[ChatMessage],
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
        client_request_id: str | None = None,
    ) -> Blocked | Completed:
        all_text = "\n".join(m.content for m in messages)

        start = time.perf_counter()
        guard = self._guard.check(all_text)
        detail: dict = {
            "reason": guard.reason,
            "input_chars": len(all_text),
            "input_sha256": hashlib.sha256(all_text.encode()).hexdigest()[:16],
        }
        if client_request_id:
            detail["client_request_id"] = client_request_id
        if self._store_content:
            detail["input"] = all_text
        recorder.record(
            "guard",
            guard.action.value,
            confidence=guard.score,
            latency_ms=_elapsed_ms(start),
            detail=detail,
        )
        if guard.blocked:
            return Blocked(guard)

        user_text = "\n".join(m.content for m in messages if m.role == "user")
        start = time.perf_counter()
        route = self._router.decide(user_text)
        recorder.record(
            "router",
            route.route.value,
            confidence=route.confidence,
            latency_ms=_elapsed_ms(start),
            detail={"reason": route.reason},
        )

        request = ProviderRequest(
            messages=tuple(messages),
            max_tokens=min(max_tokens or self._max_output_tokens, self._max_output_tokens),
            temperature=temperature,
        )
        primary = self._providers.for_route(route.route.value)
        price = self._prices.get(route.route.value, Price())
        response = await self._attempt(recorder, primary, request, route, price, fallback=False)
        if response is not None:
            return Completed(response, route, primary.name, fallback_used=False)

        fallback = self._providers.fallback
        response = await self._attempt(recorder, fallback, request, route, Price(), fallback=True)
        if response is not None:
            return Completed(response, route, fallback.name, fallback_used=True)
        raise ProviderUnavailableError("routed provider and fallback both failed")

    async def _attempt(
        self,
        recorder: TraceRecorder,
        provider: Provider,
        request: ProviderRequest,
        route: RouteDecision,
        price: Price,
        *,
        fallback: bool,
    ) -> ProviderResponse | None:
        start = time.perf_counter()
        detail: dict = {"provider": provider.name, "route": route.route.value, "fallback": fallback}
        try:
            response = await provider.complete(request)
        except ProviderError as exc:
            recorder.record(
                "provider",
                "error",
                latency_ms=_elapsed_ms(start),
                detail={**detail, "error": str(exc)},
            )
            return None

        recorder.record(
            "provider",
            "ok",
            model=response.model,
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
            cost_usd=price.cost(response.prompt_tokens, response.completion_tokens),
            latency_ms=_elapsed_ms(start),
            detail={**detail, "finish_reason": response.finish_reason},
        )
        return response
