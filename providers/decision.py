from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from providers.base import ProviderError

# Separates the policy text from the request text inside a decision `state`, so offline judges
# (and tests) can look at the request alone.
REQUEST_MARKER = "### Request"

# Tolerance for providers whose per-option probabilities do not sum to exactly 1.
_MAX_PROBABILITY_SUM = 1.05


@dataclass(frozen=True, slots=True)
class ChoiceQuestion:
    """A question with a fixed set of answers. `criteria` maps each label to when it applies."""

    key: str
    instructions: str
    criteria: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class ChoiceDecision:
    choice: str
    probabilities: Mapping[str, float]
    confidence: float
    model: str
    input_tokens: int
    output_tokens: int


@runtime_checkable
class DecisionProvider(Protocol):
    """Backend for closed-set judgements (Jev, a fine-tuned classifier, or an offline mock).

    It never generates free text. Everything the judgement depends on, including the policy, must
    be in `state` / `question`.
    """

    name: str

    async def decide(self, state: str, question: ChoiceQuestion) -> ChoiceDecision: ...


def validate_decision(decision: ChoiceDecision, question: ChoiceQuestion) -> ChoiceDecision:
    """Reject answers that do not fit the question, so a bad provider cannot steer routing."""
    labels = set(question.criteria)
    if decision.choice not in labels:
        raise ProviderError(f"decision: unknown choice {decision.choice!r}")
    if not decision.probabilities:
        raise ProviderError("decision: no probabilities returned")
    for label, p in decision.probabilities.items():
        if label not in labels:
            raise ProviderError(f"decision: unknown option {label!r} in probabilities")
        if not isinstance(p, int | float) or isinstance(p, bool) or not 0.0 <= p <= 1.0:
            raise ProviderError(f"decision: invalid probability for {label!r}")
    if sum(decision.probabilities.values()) > _MAX_PROBABILITY_SUM:
        raise ProviderError("decision: probabilities sum to more than 1")
    return decision
