from dataclasses import dataclass
from enum import StrEnum


class GuardAction(StrEnum):
    ALLOW = "allow"
    BLOCK = "block"


@dataclass(frozen=True, slots=True)
class GuardResult:
    action: GuardAction
    reason: str
    # Risk score in [0, 1]. Rule-based guards only emit 0.0 or 1.0; model-based guards will use
    # real probabilities, which is why it is recorded in the trace as `confidence`.
    score: float

    @property
    def blocked(self) -> bool:
        return self.action is GuardAction.BLOCK
