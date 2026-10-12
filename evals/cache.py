import json
import re
from pathlib import Path

from pydantic import BaseModel, Field

_VALID_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class CallRecord(BaseModel):
    """One completion from a model, as measured when it was collected."""

    content: str = ""
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0
    cost_usd: float = 0.0
    error: str | None = None


class JudgeCall(BaseModel):
    """One easy/hard judgement. On failure only `error` and `latency_ms` are meaningful."""

    choice: str | None = None
    probabilities: dict[str, float] = Field(default_factory=dict)
    confidence: float | None = None
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    cost_usd: float = 0.0
    error: str | None = None


class CachedItem(BaseModel):
    item_id: str
    # Changes whenever anything that affects the outputs changes (prompt, models, policy, limits),
    # so stale records are re-collected instead of silently reused.
    key: str
    small: CallRecord
    frontier: CallRecord
    judge: JudgeCall


class CacheMeta(BaseModel):
    name: str
    created_at: str
    dataset: str
    small: str
    frontier: str
    judge: str
    policy_version: str
    max_tokens: int
    # Prices in effect when collected, USD per 1M tokens: {"small": {"input": ..., "output": ...}}
    prices: dict[str, dict[str, float]] = Field(default_factory=dict)


class EvalCache:
    """Append-only JSONL of collected items; the last record for an item wins.

    Appending after every item makes an interrupted run resumable with no re-spend, and a
    half-written last line (crash mid-write) is skipped on load.
    """

    def __init__(self, directory: str | Path, name: str) -> None:
        if not _VALID_NAME.match(name):
            raise ValueError(f"invalid cache name {name!r} (use letters, digits, . _ -)")
        self.directory = Path(directory)
        self.name = name

    @property
    def jsonl_path(self) -> Path:
        return self.directory / f"{self.name}.jsonl"

    @property
    def meta_path(self) -> Path:
        return self.directory / f"{self.name}.meta.json"

    def load(self) -> dict[str, CachedItem]:
        if not self.jsonl_path.exists():
            return {}
        items: dict[str, CachedItem] = {}
        with open(self.jsonl_path, encoding="utf-8") as f:
            for line in f:
                try:
                    item = CachedItem.model_validate_json(line)
                except ValueError:
                    continue  # blank or truncated line
                items[item.item_id] = item
        return items

    def append(self, item: CachedItem) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        with open(self.jsonl_path, "a", encoding="utf-8", newline="\n") as f:
            f.write(item.model_dump_json() + "\n")

    def write_meta(self, meta: CacheMeta) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        self.meta_path.write_text(
            json.dumps(meta.model_dump(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    def read_meta(self) -> CacheMeta | None:
        if not self.meta_path.exists():
            return None
        return CacheMeta.model_validate_json(self.meta_path.read_text(encoding="utf-8"))
