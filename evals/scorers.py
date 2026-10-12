import re
import unicodedata
from typing import Protocol, runtime_checkable

from evals.schema import EvalItem

# Punctuation and markdown noise that models wrap around an answer ("**Paris**.", "“서울”。").
_EDGE_NOISE = " \t\r\n.,;:!?\"'`“”‘’()[]{}<>*_~…。、！？"
_NUMBER = re.compile(r"-?\d[\d,]*(?:\.\d+)?")
_NUMBER_TOLERANCE = 1e-6


def normalize(text: str) -> str:
    """NFKC (folds full-width forms), case-folded, whitespace-collapsed, edge noise removed."""
    folded = unicodedata.normalize("NFKC", text).casefold()
    return " ".join(folded.split()).strip(_EDGE_NOISE)


def extract_number(text: str) -> float | None:
    """The whole answer if it is a number, otherwise the last number in it.

    "Last number" favours conclusions like "so the answer is 42", but it will pick the wrong
    number for answers such as "70 km/h (140 / 2)". The prompts ask for the number only.
    """
    cleaned = normalize(text).replace(",", "")
    try:
        return float(cleaned)
    except ValueError:
        pass
    matches = _NUMBER.findall(normalize(text))
    return float(matches[-1].replace(",", "")) if matches else None


@runtime_checkable
class Scorer(Protocol):
    def score(self, item: EvalItem, answer: str) -> bool | None:
        """True / False when the item can be scored, None when it cannot (open-ended)."""
        ...


class RuleScorer:
    """Deterministic scoring from the item's reference list; no model involved."""

    def score(self, item: EvalItem, answer: str) -> bool | None:
        kind = item.answer_type
        if kind == "open":
            return None
        if kind == "number":
            value = extract_number(answer)
            return value is not None and any(
                abs(value - float(ref)) <= _NUMBER_TOLERANCE for ref in item.reference
            )

        got = normalize(answer)
        refs = [normalize(r) for r in item.reference]
        if kind == "exact":
            return got in refs
        if kind == "contains":
            return any(ref in got for ref in refs)
        # choice: the whole answer, or its first word ("No, it is not." -> "no").
        words = re.split(r"\W+", got)
        first = next((w for w in words if w), "")
        return got in refs or first in refs
