import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Lang = Literal["ko", "en"]
Category = Literal["factual", "transform", "math", "classify", "reasoning"]
Difficulty = Literal["easy", "hard"]
AnswerType = Literal["exact", "number", "choice", "contains", "open"]


class EvalItem(BaseModel):
    """One routing-eval prompt with a machine-checkable reference answer.

    `difficulty` is the dataset author's label (the question "could a small model answer this?"),
    not a measurement; the measured counterpart is whether the small model actually got it right.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    lang: Lang
    category: Category
    difficulty: Difficulty
    answer_type: AnswerType
    # Acceptable answers. Empty only for `open` items, which cannot be scored by rules.
    reference: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _reference_fits_answer_type(self) -> "EvalItem":
        if self.answer_type == "open":
            if self.reference:
                raise ValueError(f"{self.id}: open items must not have a reference")
            return self
        if not self.reference or any(not r.strip() for r in self.reference):
            raise ValueError(f"{self.id}: {self.answer_type} items need non-empty references")
        if self.answer_type == "number":
            for ref in self.reference:
                try:
                    float(ref)
                except ValueError as exc:
                    raise ValueError(f"{self.id}: number reference {ref!r} is not numeric") from exc
        return self


def load_items(path: str | Path) -> list[EvalItem]:
    items = []
    with open(path, encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            if not line.strip():
                continue
            try:
                items.append(EvalItem.model_validate(json.loads(line)))
            except ValueError as exc:  # json errors and pydantic validation errors
                raise ValueError(f"{path}:{line_no}: {exc}") from exc
    return items


def prompt_hash(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]


def file_hash(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]
