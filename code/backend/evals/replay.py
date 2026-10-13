from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from evals.cache import CachedItem
from evals.schema import EvalItem
from evals.scorers import Scorer
from providers.base import ProviderError
from providers.decision import ChoiceDecision, ChoiceQuestion
from router.base import Router
from router.hybrid_router import HybridConfig, HybridRouter
from router.rule_router import RouterConfig, RuleRouter

Mode = Literal["all_small", "all_frontier", "rules", "hybrid", "judge_only"]


@dataclass(frozen=True, slots=True)
class ConfigSpec:
    name: str
    mode: Mode
    tau: float | None = None


@dataclass(frozen=True, slots=True)
class ItemOutcome:
    item_id: str
    lang: str
    category: str
    difficulty: str
    route: str
    reason: str
    correct: bool | None
    cost_usd: float
    latency_ms: int
    judge_consulted: bool
    judge_failed: bool
    p_easy: float | None


@dataclass(frozen=True, slots=True)
class ModelScores:
    small: bool | None
    frontier: bool | None


@dataclass(frozen=True, slots=True)
class Usable:
    items: list[EvalItem]
    excluded: list[tuple[str, str]]  # (item id, reason)


def default_configs(taus: Sequence[float]) -> list[ConfigSpec]:
    specs = [
        ConfigSpec("all_small", "all_small"),
        ConfigSpec("all_frontier", "all_frontier"),
        ConfigSpec("rules", "rules"),
    ]
    specs += [ConfigSpec(f"hybrid@{t:g}", "hybrid", t) for t in taus]
    specs += [ConfigSpec(f"judge_only@{t:g}", "judge_only", t) for t in taus]
    return specs


def usable_items(items: Sequence[EvalItem], cached: Mapping[str, CachedItem]) -> Usable:
    """Items with both model answers collected. A failed judge call is fine: that is an outage."""
    usable: list[EvalItem] = []
    excluded: list[tuple[str, str]] = []
    for item in items:
        record = cached.get(item.id)
        if record is None:
            excluded.append((item.id, "not collected"))
        elif record.small.error:
            excluded.append((item.id, "small model call failed"))
        elif record.frontier.error:
            excluded.append((item.id, "frontier model call failed"))
        else:
            usable.append(item)
    return Usable(usable, excluded)


def score_cached(
    items: Sequence[EvalItem], cached: Mapping[str, CachedItem], scorer: Scorer
) -> dict[str, ModelScores]:
    return {
        item.id: ModelScores(
            small=scorer.score(item, cached[item.id].small.content),
            frontier=scorer.score(item, cached[item.id].frontier.content),
        )
        for item in items
    }


class CachedDecisionProvider:
    """Answers with the judgement recorded at collect time, so the real router code can be re-run.

    `current` is set to the item being replayed before each routing call.
    """

    name = "cached-judge"

    def __init__(self) -> None:
        self.current: CachedItem | None = None

    async def decide(self, state: str, question: ChoiceQuestion) -> ChoiceDecision:
        if self.current is None:
            raise ProviderError("cached-judge: no item selected")
        call = self.current.judge
        if call.error is not None or call.choice is None:
            raise ProviderError(call.error or "cached-judge: no judgement recorded")
        return ChoiceDecision(
            choice=call.choice,
            probabilities=call.probabilities,
            confidence=call.confidence if call.confidence is not None else 0.0,
            model=call.model,
            input_tokens=call.input_tokens,
            output_tokens=call.output_tokens,
        )


def _build_router(
    spec: ConfigSpec, judge: CachedDecisionProvider, rules: RuleRouter
) -> Router | None:
    if spec.mode in ("all_small", "all_frontier"):
        return None
    if spec.mode == "rules":
        return rules
    if spec.tau is None:
        raise ValueError(f"{spec.name}: {spec.mode} needs a threshold")
    return HybridRouter(rules, judge, HybridConfig(spec.tau, judge_only=spec.mode == "judge_only"))


async def replay(
    items: Sequence[EvalItem],
    cached: Mapping[str, CachedItem],
    spec: ConfigSpec,
    scorer: Scorer,
    rules_config: RouterConfig | None = None,
) -> list[ItemOutcome]:
    """What would `spec` have done on each item, given the answers collected earlier?

    Routing runs through the gateway's own `RuleRouter` / `HybridRouter`. The cost and latency of a
    judge call are charged from the recorded values (whenever the router consulted the judge,
    including when it failed); the router's own timing in this offline run is ignored.
    """
    judge = CachedDecisionProvider()
    router = _build_router(spec, judge, RuleRouter(rules_config))
    outcomes: list[ItemOutcome] = []
    for item in items:
        record = cached[item.id]
        judge.current = record
        decision = await router.route(item.prompt) if router else None
        if decision is None:
            route, reason = (
                ("small", "fixed") if spec.mode == "all_small" else ("frontier", "fixed")
            )
        else:
            route, reason = decision.route.value, decision.reason

        call = record.small if route == "small" else record.frontier
        consulted = decision is not None and decision.judge is not None
        failed = consulted and not decision.judge.ok
        p_easy = decision.detail.get("p_easy") if decision is not None else None
        outcomes.append(
            ItemOutcome(
                item_id=item.id,
                lang=item.lang,
                category=item.category,
                difficulty=item.difficulty,
                route=route,
                reason=reason,
                correct=scorer.score(item, call.content),
                cost_usd=call.cost_usd
                + (record.judge.cost_usd if consulted and not failed else 0.0),
                latency_ms=call.latency_ms + (record.judge.latency_ms if consulted else 0),
                judge_consulted=consulted,
                judge_failed=failed,
                p_easy=p_easy,
            )
        )
    return outcomes
