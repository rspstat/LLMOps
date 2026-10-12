from providers.base import ProviderError, estimate_tokens
from providers.decision import REQUEST_MARKER, ChoiceDecision, ChoiceQuestion


class MockDecisionProvider:
    """Deterministic offline judge for the easy/hard routing question. Never touches the network.

    The "difficulty" is just request length, which is enough to exercise promotion logic but says
    nothing about real judging quality. Pass `fail=True` to simulate an outage.
    """

    def __init__(self, name: str = "mock-judge", *, fail: bool = False) -> None:
        self.name = name
        self.fail = fail
        self.calls = 0

    async def decide(self, state: str, question: ChoiceQuestion) -> ChoiceDecision:
        self.calls += 1
        if self.fail:
            raise ProviderError(f"{self.name}: simulated outage")

        labels = list(question.criteria)
        request = state.partition(REQUEST_MARKER)[2] or state
        # Longer requests look harder: 0.10 for empty up to 0.95 at ~850+ chars.
        hard = min(0.95, 0.10 + len(request.strip()) / 1000)
        if "easy" in labels and "hard" in labels:
            probabilities = {"easy": round(1 - hard, 4), "hard": round(hard, 4)}
        else:
            probabilities = {label: round(1 / len(labels), 4) for label in labels}
        choice = max(probabilities, key=lambda label: probabilities[label])
        return ChoiceDecision(
            choice=choice,
            probabilities=probabilities,
            confidence=probabilities[choice],
            model=self.name,
            input_tokens=estimate_tokens(state),
            output_tokens=1,
        )
