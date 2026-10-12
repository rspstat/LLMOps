import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from gateway.trace import SqliteTraceStore, TraceEvent, TraceRecorder, create_trace_store


@pytest.fixture
def store(tmp_path):
    return SqliteTraceStore(tmp_path / "traces.sqlite3")


def make_event(request_id="req-1", seq=0, **overrides) -> TraceEvent:
    fields = {"stage": "guard", "decision": "allow"} | overrides
    return TraceEvent(request_id=request_id, seq=seq, **fields)


# --- TraceStore contract: the same tests must hold for any future implementation -----------


def test_unknown_request_returns_empty_list(store):
    assert store.get("nope") == []


def test_round_trips_all_fields(store):
    event = make_event(
        stage="provider",
        decision="small",
        confidence=0.5,
        model="tiny",
        prompt_tokens=7,
        completion_tokens=3,
        cost_usd=0.000123,
        latency_ms=42,
        detail={"fallback": True, "메모": "한글"},
    )
    store.write_many([event])
    assert store.get("req-1") == [event]


def test_nullable_fields_stay_none(store):
    store.write_many([make_event()])
    [loaded] = store.get("req-1")
    assert loaded.confidence is None and loaded.cost_usd is None and loaded.latency_ms is None
    assert loaded.detail == {}


def test_events_come_back_ordered_by_seq_and_isolated_by_request(store):
    store.write_many(
        [
            make_event(seq=2, stage="provider", decision="x"),
            make_event(seq=0, stage="guard", decision="allow"),
            make_event(seq=1, stage="router", decision="small"),
            make_event(request_id="req-2", seq=0),
        ]
    )
    assert [e.stage for e in store.get("req-1")] == ["guard", "router", "provider"]
    assert len(store.get("req-2")) == 1


def test_write_many_is_atomic(store):
    batch = [make_event(seq=0), make_event(seq=0)]  # duplicate primary key
    with pytest.raises(sqlite3.IntegrityError):
        store.write_many(batch)
    assert store.get("req-1") == []


def test_concurrent_writers_do_not_lose_events(store):
    def write(i: int) -> None:
        store.write_many([make_event(request_id=f"req-{i}")])

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(write, range(40)))
    assert all(len(store.get(f"req-{i}")) == 1 for i in range(40))


# --- SQLite specifics ----------------------------------------------------------------------


def test_data_persists_across_store_instances(tmp_path):
    path = tmp_path / "t.sqlite3"
    SqliteTraceStore(path).write_many([make_event()])
    assert len(SqliteTraceStore(path).get("req-1")) == 1


def test_creates_missing_parent_directory(tmp_path):
    SqliteTraceStore(tmp_path / "nested" / "dir" / "t.sqlite3")
    assert (tmp_path / "nested" / "dir" / "t.sqlite3").exists()


# --- recorder and factory ------------------------------------------------------------------


def test_recorder_numbers_events_in_order():
    recorder = TraceRecorder("req-9")
    recorder.record("guard", "allow", confidence=0.0)
    recorder.record("router", "small")
    assert [(e.request_id, e.seq, e.stage) for e in recorder.events] == [
        ("req-9", 0, "guard"),
        ("req-9", 1, "router"),
    ]


def test_factory_builds_sqlite_store_from_url(tmp_path):
    path = tmp_path / "f.sqlite3"
    store = create_trace_store(f"sqlite:///{path.as_posix()}")
    store.write_many([make_event()])
    assert path.exists()


def test_factory_rejects_memory_postgres_and_unknown_schemes():
    with pytest.raises(ValueError, match="file path"):
        create_trace_store("sqlite:///:memory:")
    with pytest.raises(NotImplementedError, match="PostgreSQL"):
        create_trace_store("postgresql://u:p@localhost/db")
    with pytest.raises(ValueError, match="mysql"):
        create_trace_store("mysql://localhost/db")
