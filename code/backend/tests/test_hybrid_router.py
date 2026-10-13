import inspect

import pytest

from providers.base import ProviderError
from providers.decision import REQUEST_MARKER, ChoiceDecision, ChoiceQuestion
from providers.mock_decision import MockDecisionProvider
from router.base import Route
from router.hybrid_router import HybridConfig, HybridRouter
from router.policy import POLICY_TEXT, POLICY_VERSION, QUESTION, build_state
from router.rule_router import RouterConfig, RuleRouter


class ScriptedJudge:
    """Returns fixed probabilities and remembers what it was asked."""

    name = "scripted"

    def __init__(self, p_easy: float | None = None, *, choice: str | None = None, error=None):
        self.p_easy = p_easy
        self.choice = choice
        self.error = error
        self.calls: list[tuple[str, ChoiceQuestion]] = []

    async def decide(self, state: str, question: ChoiceQuestion) -> ChoiceDecision:
        self.calls.append((state, question))
        if self.error is not None:
            raise self.error
        p = self.p_easy
        probabilities = {"easy": p, "hard": round(1 - p, 4)}
        choice = self.choice or ("easy" if p >= 0.5 else "hard")
        return ChoiceDecision(
            choice, probabilities, max(probabilities.values()), "scripted-1", 40, 2
        )


def make_router(judge, *, threshold=0.7, judge_only=False, long_chars=600) -> HybridRouter:
    rules = RuleRouter(RouterConfig(long_prompt_chars=long_chars))
    return HybridRouter(rules, judge, HybridConfig(threshold, judge_only))


def test_both_routers_expose_an_async_route_method():
    # The pipeline awaits `route()`, so every router must provide it as a coroutine function.
    assert inspect.iscoroutinefunction(make_router(ScriptedJudge(0.9)).route)
    assert inspect.iscoroutinefunction(RuleRouter().route)


@pytest.mark.anyio
async def test_explicit_rule_hit_skips_the_judge_entirely():
    judge = ScriptedJudge(0.99)
    decision = await make_router(judge).route("please analyze this")
    assert decision.route is Route.FRONTIER
    assert decision.reason == "keyword:analyze"
    assert decision.judge is None
    assert judge.calls == []


@pytest.mark.anyio
async def test_confident_easy_goes_to_small():
    decision = await make_router(ScriptedJudge(0.92)).route("what is 2+2")
    assert decision.route is Route.SMALL
    assert decision.reason == "judge_easy"
    assert decision.confidence == 0.92
    assert decision.judge.ok and decision.judge.choice == "easy"
    assert decision.judge.probabilities == {"easy": 0.92, "hard": 0.08}
    assert (decision.judge.input_tokens, decision.judge.output_tokens) == (40, 2)
    assert decision.judge.policy_version == POLICY_VERSION
    assert decision.detail["rule_hint"] == "default_small"


@pytest.mark.anyio
async def test_threshold_is_inclusive():
    assert (await make_router(ScriptedJudge(0.7)).route("hi")).route is Route.SMALL
    promoted = await make_router(ScriptedJudge(0.69, choice="easy")).route("hi")
    assert promoted.route is Route.FRONTIER
    assert promoted.reason == "promoted_low_confidence"
    assert promoted.confidence == 0.69


@pytest.mark.anyio
async def test_threshold_is_configurable():
    decision = await make_router(ScriptedJudge(0.6), threshold=0.5).route("hi")
    assert decision.route is Route.SMALL


@pytest.mark.anyio
async def test_hard_goes_to_frontier():
    decision = await make_router(ScriptedJudge(0.1)).route("design a database")
    assert decision.route is Route.FRONTIER
    assert decision.reason == "judge_hard"


@pytest.mark.anyio
async def test_inconsistent_easy_choice_with_low_p_easy_is_not_trusted():
    # choice says easy, but the numbers do not reach the threshold: promote.
    decision = await make_router(ScriptedJudge(0.4, choice="easy")).route("hi")
    assert decision.route is Route.FRONTIER


@pytest.mark.anyio
async def test_judge_receives_policy_question_and_request_text():
    judge = ScriptedJudge(0.9)
    await make_router(judge).route("translate this sentence")
    [(state, question)] = judge.calls
    assert state == build_state("translate this sentence")
    assert state.startswith(POLICY_TEXT)
    assert state.endswith(f"{REQUEST_MARKER}\ntranslate this sentence")
    assert question is QUESTION


@pytest.mark.anyio
@pytest.mark.parametrize(
    "error", [ProviderError("scripted: HTTP 500"), RuntimeError("boom"), TimeoutError()]
)
async def test_judge_failure_keeps_the_rule_decision_and_records_why(error):
    judge = ScriptedJudge(error=error)
    decision = await make_router(judge).route("hello there")
    assert decision.route is Route.SMALL  # what the rules said
    assert decision.reason == "judge_unavailable"
    assert not decision.judge.ok
    assert decision.judge.error == (
        str(error) if isinstance(error, ProviderError) else type(error).__name__
    )
    assert decision.judge.choice is None


@pytest.mark.anyio
async def test_invalid_judge_answer_is_treated_as_failure():
    judge = ScriptedJudge(0.9, choice="medium")
    decision = await make_router(judge).route("hello")
    assert decision.reason == "judge_unavailable"
    assert "unknown choice" in decision.judge.error


@pytest.mark.anyio
async def test_judge_only_mode_asks_even_when_a_rule_fires():
    judge = ScriptedJudge(0.95)
    decision = await make_router(judge, judge_only=True).route("please analyze this")
    assert len(judge.calls) == 1
    assert decision.route is Route.SMALL  # the judge overrides the keyword rule
    assert decision.detail["rule_hint"] == "keyword:analyze"


@pytest.mark.anyio
async def test_judge_only_failure_falls_back_to_the_rule_that_fired():
    judge = ScriptedJudge(error=ProviderError("down"))
    decision = await make_router(judge, judge_only=True).route("please analyze this")
    assert decision.route is Route.FRONTIER
    assert decision.reason == "judge_unavailable"


@pytest.mark.anyio
async def test_with_mock_judge_short_is_small_and_longer_request_is_promoted():
    router = make_router(MockDecisionProvider())
    assert (await router.route("hi")).route is Route.SMALL
    assert (await router.route("x" * 300)).route is Route.FRONTIER  # still under the length rule


@pytest.mark.anyio
async def test_rule_router_also_works_as_a_router():
    decision = await RuleRouter().route("hello")
    assert decision.route is Route.SMALL and decision.judge is None
