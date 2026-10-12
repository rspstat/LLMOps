import pytest

from providers.base import ProviderError
from providers.decision import (
    REQUEST_MARKER,
    ChoiceDecision,
    ChoiceQuestion,
    DecisionProvider,
    validate_decision,
)
from providers.mock_decision import MockDecisionProvider

QUESTION = ChoiceQuestion("difficulty", "How hard?", {"easy": "simple", "hard": "complex"})


def state_for(request: str) -> str:
    return f"policy text\n\n{REQUEST_MARKER}\n{request}"


def decision(**overrides) -> ChoiceDecision:
    fields = {
        "choice": "easy",
        "probabilities": {"easy": 0.8, "hard": 0.2},
        "confidence": 0.8,
        "model": "m",
        "input_tokens": 1,
        "output_tokens": 1,
    }
    return ChoiceDecision(**(fields | overrides))


def test_mock_satisfies_protocol():
    assert isinstance(MockDecisionProvider(), DecisionProvider)


@pytest.mark.anyio
async def test_short_request_is_easy_and_long_request_is_hard():
    judge = MockDecisionProvider()
    short = await judge.decide(state_for("hi"), QUESTION)
    long = await judge.decide(state_for("x" * 900), QUESTION)
    assert short.choice == "easy" and short.probabilities["easy"] > 0.85
    assert long.choice == "hard" and long.probabilities["hard"] == 0.95


@pytest.mark.anyio
async def test_policy_text_does_not_influence_the_mock():
    judge = MockDecisionProvider()
    plain = await judge.decide(f"{REQUEST_MARKER}\nhi", QUESTION)
    with_policy = await judge.decide(state_for("hi"), QUESTION)
    assert plain.probabilities == with_policy.probabilities


@pytest.mark.anyio
async def test_mock_is_deterministic_valid_and_counts_calls():
    judge = MockDecisionProvider()
    first = await judge.decide(state_for("some request"), QUESTION)
    second = await judge.decide(state_for("some request"), QUESTION)
    assert first == second and judge.calls == 2
    assert validate_decision(first, QUESTION) is first
    assert first.input_tokens > 0 and first.output_tokens == 1
    assert first.confidence == max(first.probabilities.values())


@pytest.mark.anyio
async def test_failing_mock_raises_provider_error():
    with pytest.raises(ProviderError):
        await MockDecisionProvider(fail=True).decide(state_for("hi"), QUESTION)


@pytest.mark.parametrize(
    "bad",
    [
        {"choice": "medium"},
        {"probabilities": {}},
        {"probabilities": {"easy": 0.5, "unknown": 0.5}},
        {"probabilities": {"easy": 1.2, "hard": 0.0}},
        {"probabilities": {"easy": -0.1, "hard": 0.5}},
        {"probabilities": {"easy": 0.9, "hard": 0.9}},
        {"probabilities": {"easy": True, "hard": 0.0}},
    ],
)
def test_validate_rejects_answers_that_do_not_fit_the_question(bad):
    with pytest.raises(ProviderError):
        validate_decision(decision(**bad), QUESTION)


def test_validate_accepts_probabilities_summing_slightly_over_one():
    ok = decision(probabilities={"easy": 0.52, "hard": 0.52})
    assert validate_decision(ok, QUESTION) is ok
