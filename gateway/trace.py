import json
import sqlite3
from collections.abc import Sequence
from contextlib import closing
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

SQLITE_URL_PREFIX = "sqlite:///"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True, slots=True)
class TraceEvent:
    """One pipeline stage (guard / router / provider) of one request."""

    request_id: str
    seq: int
    stage: str
    decision: str
    confidence: float | None = None
    model: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cost_usd: float | None = None
    latency_ms: int | None = None
    detail: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_now_iso)


class TraceRecorder:
    """Collects the ordered events of a single request, to be flushed to a store at the end."""

    def __init__(self, request_id: str) -> None:
        self.request_id = request_id
        self.events: list[TraceEvent] = []

    def record(self, stage: str, decision: str, **fields: Any) -> TraceEvent:
        event = TraceEvent(
            request_id=self.request_id,
            seq=len(self.events),
            stage=stage,
            decision=decision,
            **fields,
        )
        self.events.append(event)
        return event


class TraceStore(Protocol):
    """Persistence for trace events. Implementations must be safe to call from worker threads."""

    def write_many(self, events: Sequence[TraceEvent]) -> None: ...

    def get(self, request_id: str) -> list[TraceEvent]:
        """All events of a request ordered by `seq`; empty list if unknown."""
        ...


# Column types are deliberately portable (TEXT / INTEGER / DOUBLE PRECISION, composite primary
# key, no AUTOINCREMENT) so the same DDL moves to PostgreSQL later; JSON and timestamps are TEXT
# for now and become JSONB / TIMESTAMPTZ there.
_SCHEMA = """
CREATE TABLE IF NOT EXISTS trace_events (
    request_id        TEXT NOT NULL,
    seq               INTEGER NOT NULL,
    stage             TEXT NOT NULL,
    decision          TEXT NOT NULL,
    confidence        DOUBLE PRECISION,
    model             TEXT,
    prompt_tokens     INTEGER,
    completion_tokens INTEGER,
    cost_usd          DOUBLE PRECISION,
    latency_ms        INTEGER,
    detail_json       TEXT NOT NULL,
    created_at        TEXT NOT NULL,
    PRIMARY KEY (request_id, seq)
)
"""

_COLUMNS = (
    "request_id, seq, stage, decision, confidence, model, prompt_tokens, completion_tokens, "
    "cost_usd, latency_ms, detail_json, created_at"
)


class SqliteTraceStore:
    """File-backed SQLite store. Opens a short-lived connection per call, so it is thread-safe."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn, conn:
            conn.execute(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path, timeout=10)

    def write_many(self, events: Sequence[TraceEvent]) -> None:
        rows = [
            (
                e.request_id,
                e.seq,
                e.stage,
                e.decision,
                e.confidence,
                e.model,
                e.prompt_tokens,
                e.completion_tokens,
                e.cost_usd,
                e.latency_ms,
                json.dumps(e.detail, ensure_ascii=False, sort_keys=True),
                e.created_at,
            )
            for e in events
        ]
        placeholders = ", ".join("?" * 12)
        with closing(self._connect()) as conn, conn:  # `conn` as context manager = transaction
            conn.executemany(f"INSERT INTO trace_events ({_COLUMNS}) VALUES ({placeholders})", rows)

    def get(self, request_id: str) -> list[TraceEvent]:
        with closing(self._connect()) as conn:
            cursor = conn.execute(
                f"SELECT {_COLUMNS} FROM trace_events WHERE request_id = ? ORDER BY seq",
                (request_id,),
            )
            rows = cursor.fetchall()
        return [
            TraceEvent(
                request_id=r[0],
                seq=r[1],
                stage=r[2],
                decision=r[3],
                confidence=r[4],
                model=r[5],
                prompt_tokens=r[6],
                completion_tokens=r[7],
                cost_usd=r[8],
                latency_ms=r[9],
                detail=json.loads(r[10]),
                created_at=r[11],
            )
            for r in rows
        ]


def create_trace_store(database_url: str) -> TraceStore:
    if database_url.startswith(SQLITE_URL_PREFIX):
        path = database_url[len(SQLITE_URL_PREFIX) :]
        if not path or path == ":memory:":
            raise ValueError("SQLite trace store needs a file path, not an in-memory database")
        return SqliteTraceStore(path)
    if database_url.startswith(("postgresql://", "postgres://")):
        raise NotImplementedError("PostgreSQL trace store is planned (see docs/architecture.md)")
    raise ValueError(f"Unsupported DATABASE_URL scheme: {database_url.split(':', 1)[0]!r}")
