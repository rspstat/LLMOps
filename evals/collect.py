import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from evals.cache import CachedItem, CallRecord, EvalCache, JudgeCall
from evals.schema import EvalItem, prompt_hash
from gateway.pipeline import Price
from providers.base import (
    ChatMessage,
    Provider,
    ProviderError,
    ProviderRequest,
    estimate_tokens,
)
from providers.decision import DecisionProvider, validate_decision
from router.policy import POLICY_VERSION, QUESTION, build_state


@dataclass(frozen=True, slots=True)
class ModelTarget:
    provider: Provider
    # Stable description of what is behind the provider (e.g. "slm:qwen-0.5b"). Part of the
    # cache key, because a provider's `name` does not change when its model does.
    identity: str
    price: Price


@dataclass(frozen=True, slots=True)
class JudgeTarget:
    provider: DecisionProvider
    identity: str
    price: Price


@dataclass(slots=True)
class CollectStats:
    total: int = 0
    reused: int = 0
    collected: int = 0
    calls: int = 0
    spent_usd: float = 0.0
    stopped_by_budget: bool = False
    failed_items: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class Estimate:
    items: int
    calls: int
    input_tokens: int
    max_output_tokens: int
    cost_usd: float


def key_from_parts(
    item: EvalItem,
    small: str,
    frontier: str,
    judge: str,
    policy_version: str,
    max_tokens: int,
) -> str:
    return "|".join(
        [prompt_hash(item.prompt), small, frontier, judge, policy_version, str(max_tokens)]
    )


def make_key(
    item: EvalItem,
    small: ModelTarget,
    frontier: ModelTarget,
    judge: JudgeTarget,
    max_tokens: int,
) -> str:
    return key_from_parts(
        item, small.identity, frontier.identity, judge.identity, POLICY_VERSION, max_tokens
    )


def pending_items(
    items: Sequence[EvalItem],
    cache: EvalCache,
    small: ModelTarget,
    frontier: ModelTarget,
    judge: JudgeTarget,
    max_tokens: int,
) -> list[EvalItem]:
    """Items that still need real calls: not cached, or cached under a different key."""
    cached = cache.load()
    return [
        item
        for item in items
        if item.id not in cached
        or cached[item.id].key != make_key(item, small, frontier, judge, max_tokens)
    ]


def estimate(
    items: Sequence[EvalItem],
    small: ModelTarget,
    frontier: ModelTarget,
    judge: JudgeTarget,
    max_tokens: int,
) -> Estimate:
    """Rough upper bound before spending anything: every answer is assumed to hit `max_tokens`.

    Token counts use the same ~4 chars/token heuristic as the mock provider, so treat the cost as
    an order of magnitude, not a quote.
    """
    input_tokens = 0
    cost = 0.0
    for item in items:
        prompt_tokens = estimate_tokens(item.prompt)
        judge_tokens = estimate_tokens(build_state(item.prompt))
        input_tokens += judge_tokens + 2 * prompt_tokens
        cost += judge.price.cost(judge_tokens, 1)
        cost += small.price.cost(prompt_tokens, max_tokens)
        cost += frontier.price.cost(prompt_tokens, max_tokens)
    return Estimate(
        items=len(items),
        calls=3 * len(items),
        input_tokens=input_tokens,
        max_output_tokens=2 * max_tokens * len(items),
        cost_usd=cost,
    )


def _elapsed_ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


async def _complete(target: ModelTarget, item: EvalItem, max_tokens: int) -> CallRecord:
    request = ProviderRequest(
        messages=(ChatMessage("user", item.prompt),), max_tokens=max_tokens, temperature=0.0
    )
    start = time.perf_counter()
    try:
        response = await target.provider.complete(request)
    except ProviderError as exc:
        return CallRecord(error=str(exc), latency_ms=_elapsed_ms(start))
    return CallRecord(
        content=response.content,
        model=response.model,
        prompt_tokens=response.prompt_tokens,
        completion_tokens=response.completion_tokens,
        latency_ms=_elapsed_ms(start),
        cost_usd=target.price.cost(response.prompt_tokens, response.completion_tokens),
    )


async def _judge(target: JudgeTarget, item: EvalItem) -> JudgeCall:
    start = time.perf_counter()
    try:
        decision = validate_decision(
            await target.provider.decide(build_state(item.prompt), QUESTION), QUESTION
        )
    except Exception as exc:  # same rule as the router: a failing judge is data, not a crash
        error = str(exc) if isinstance(exc, ProviderError) else type(exc).__name__
        return JudgeCall(error=error, latency_ms=_elapsed_ms(start))
    return JudgeCall(
        choice=decision.choice,
        probabilities=dict(decision.probabilities),
        confidence=decision.confidence,
        model=decision.model,
        input_tokens=decision.input_tokens,
        output_tokens=decision.output_tokens,
        latency_ms=_elapsed_ms(start),
        cost_usd=target.price.cost(decision.input_tokens, decision.output_tokens),
    )


async def collect(
    items: Sequence[EvalItem],
    cache: EvalCache,
    *,
    small: ModelTarget,
    frontier: ModelTarget,
    judge: JudgeTarget,
    max_tokens: int,
    budget_usd: float | None = None,
    progress: Callable[[str], None] | None = None,
) -> CollectStats:
    """Call the judge, the small model and the frontier model once per item and cache the results.

    Calls run one after another on purpose: latency is the thing being measured, and concurrent
    requests would contaminate it. Failures are stored in the record and the run continues. The
    run stops before starting a new item once `budget_usd` has been spent (actual cost so far).
    """
    stats = CollectStats(total=len(items))
    cached = cache.load()
    for index, item in enumerate(items, start=1):
        key = make_key(item, small, frontier, judge, max_tokens)
        if item.id in cached and cached[item.id].key == key:
            stats.reused += 1
            continue
        if budget_usd is not None and stats.spent_usd >= budget_usd:
            stats.stopped_by_budget = True
            break

        record = CachedItem(
            item_id=item.id,
            key=key,
            judge=await _judge(judge, item),
            small=await _complete(small, item, max_tokens),
            frontier=await _complete(frontier, item, max_tokens),
        )
        cache.append(record)
        stats.collected += 1
        stats.calls += 3
        stats.spent_usd += record.judge.cost_usd + record.small.cost_usd + record.frontier.cost_usd
        if any(part.error for part in (record.judge, record.small, record.frontier)):
            stats.failed_items.append(item.id)
        if progress:
            progress(f"[{index}/{len(items)}] {item.id} (spent ${stats.spent_usd:.6f})")
    return stats
