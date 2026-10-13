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


_HEDGE_WINDOW = 3  # words at the start of a choice answer that are checked for hedging


def _label_matches(word: str, label: str) -> bool:
    """`word` is `label`, or a Korean label followed by a particle or ending ("민수가").

    Single characters stay exact ("예" must not match "예를"), as do ASCII labels ("no"/"not").
    """
    return word == label or (len(label) >= 2 and not label.isascii() and word.startswith(label))


def _mentions_several(words: list[str], options: list[str]) -> bool:
    labels = [normalize(o) for o in options]
    found = {label for label in labels if any(_label_matches(w, label) for w in words)}
    return len(found) >= 2


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
        # choice: the whole answer, or its first word ("No, it is not." -> "no"), unless the
        # opening words name several of the offered options (a hedge).
        words = [w for w in re.split(r"\W+", got) if w]
        first = words[0] if words else ""
        if item.options and _mentions_several(words[:_HEDGE_WINDOW], item.options):
            return False
        if got in refs or first in refs:
            return True
        return any(_label_matches(first, ref) for ref in refs)
