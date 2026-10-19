import logging
import time
from dataclasses import dataclass, field, replace

from providers.base import ProviderError
from providers.decision import ChoiceDecision, DecisionProvider, validate_decision
from router.base import JudgeRecord, Route, RouteDecision
from router.policy import DEFAULT_POLICY_VERSION, Policy, build_state, get_policy
from router.rule_router import RuleRouter

logger = logging.getLogger("llmops.router")


@dataclass(frozen=True, slots=True)
class HybridConfig:
    # The small model is used only when the judge says "easy" with at least this probability;
    # everything else is promoted to the frontier model.
    promote_threshold: float = 0.7
    # Ask the judge for every request instead of letting an explicit rule short-circuit it.
    # Used to compare the rules against the judge on the same traffic.
    judge_only: bool = False
    # The wording sent to the judge with every request; its version is recorded in the trace.
    policy: Policy = field(default_factory=lambda: get_policy(DEFAULT_POLICY_VERSION))


class HybridRouter:
    """Rules first, then the judge, then confidence-based promotion.

    1. An explicit rule hit (rules chose `frontier`) is final and costs no judge call.
    2. Otherwise the judge answers easy/hard with probabilities; `small` needs p(easy) >= threshold.
    3. If the judge fails for any reason, the rule decision stands and the trace says why.
    """

    def __init__(
        self, rules: RuleRouter, judge: DecisionProvider, config: HybridConfig | None = None
    ) -> None:
        self.rules = rules
        self.judge = judge
        self.config = config or HybridConfig()

    async def route(self, text: str) -> RouteDecision:
        rule = self.rules.decide(text)
        if not self.config.judge_only and rule.route is Route.FRONTIER:
            return rule

        policy = self.config.policy
        start = time.perf_counter()
        try:
            decision = validate_decision(
                await self.judge.decide(build_state(text, policy), policy.question),
                policy.question,
            )
        except Exception as exc:  # a broken judge must never take request serving down
            # Only ProviderError text is known to be safe to store; other errors keep their type.
            error = str(exc) if isinstance(exc, ProviderError) else type(exc).__name__
            logger.warning("judge %s failed: %s", self.judge.name, error)
            record = JudgeRecord(
                provider=self.judge.name,
                latency_ms=_elapsed_ms(start),
                policy_version=policy.version,
                error=error,
            )
            return replace(rule, reason="judge_unavailable", judge=record)

        record = JudgeRecord(
            provider=self.judge.name,
            latency_ms=_elapsed_ms(start),
            policy_version=policy.version,
            choice=decision.choice,
            probabilities=dict(decision.probabilities),
            confidence=decision.confidence,
            model=decision.model,
            input_tokens=decision.input_tokens,
            output_tokens=decision.output_tokens,
        )
        return self._decide(rule, decision, record)

    def _decide(
        self, rule: RouteDecision, decision: ChoiceDecision, record: JudgeRecord
    ) -> RouteDecision:
        p_easy = decision.probabilities.get("easy", 0.0)
        threshold = self.config.promote_threshold
        if decision.choice == "easy" and p_easy >= threshold:
            route, reason = Route.SMALL, "judge_easy"
        elif decision.choice == "hard":
            route, reason = Route.FRONTIER, "judge_hard"
        else:
            route, reason = Route.FRONTIER, "promoted_low_confidence"
        return RouteDecision(
            route,
            reason,
            p_easy,
            judge=record,
            detail={
                "threshold": threshold,
                "p_easy": p_easy,
                "policy_version": self.config.policy.version,
                "rule_hint": rule.reason,
            },
        )


def _elapsed_ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)
