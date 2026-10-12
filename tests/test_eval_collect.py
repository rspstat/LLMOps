import pytest

from evals.cache import CachedItem, CacheMeta, CallRecord, EvalCache, JudgeCall
from evals.collect import (
    JudgeTarget,
    ModelTarget,
    collect,
    estimate,
    make_key,
    pending_items,
)
from evals.schema import EvalItem
from gateway.pipeline import Price
from providers.base import ProviderError, ProviderRequest, ProviderResponse
from providers.decision import ChoiceDecision, ChoiceQuestion


def make_item(n: int, prompt: str | None = None) -> EvalItem:
    return EvalItem(
        id=f"i{n}",
        prompt=prompt or f"question {n} " * 3,
        lang="en",
        category="math",
        difficulty="easy",
        answer_type="exact",
        reference=["x"],
    )


class FakeModel:
    def __init__(self, name: str, *, fail_on: set[str] = frozenset()):
        self.name = name
        self.fail_on = set(fail_on)
        self.calls: list[ProviderRequest] = []

    async def complete(self, request: ProviderRequest) -> ProviderResponse:
        self.calls.append(request)
        prompt = request.messages[-1].content
        if any(marker in prompt for marker in self.fail_on):
            raise ProviderError(f"{self.name}: HTTP 500")
        return ProviderResponse(f"{self.name}-answer", self.name, 10, 2)


class FakeJudge:
    def __init__(self, *, choice="easy", fail=False, p_easy=0.9):
        self.name = "fake-judge"
        self.choice, self.fail, self.p_easy = choice, fail, p_easy
        self.calls = 0

    async def decide(self, state: str, question: ChoiceQuestion) -> ChoiceDecision:
        self.calls += 1
        if self.fail:
            raise ProviderError("fake-judge: down")
        probs = {"easy": self.p_easy, "hard": round(1 - self.p_easy, 4)}
        return ChoiceDecision(self.choice, probs, max(probs.values()), "fake-judge-1", 100, 1)


def targets(
    small=None, frontier=None, judge=None, *, small_id="s1", frontier_id="f1", judge_id="j1"
):
    # $1 / $2 per 1M tokens (small), $10 / $20 (frontier), $5 / $0 (judge): easy to hand-check.
    return {
        "small": ModelTarget(small or FakeModel("small"), small_id, Price(1.0, 2.0)),
        "frontier": ModelTarget(frontier or FakeModel("frontier"), frontier_id, Price(10.0, 20.0)),
        "judge": JudgeTarget(judge or FakeJudge(), judge_id, Price(5.0, 0.0)),
    }


@pytest.fixture
def cache(tmp_path):
    return EvalCache(tmp_path / "cache", "run1")


@pytest.mark.anyio
async def test_collects_one_complete_record_per_item_with_measured_cost(cache):
    items = [make_item(1), make_item(2)]
    stats = await collect(items, cache, **targets(), max_tokens=64)

    assert (stats.total, stats.collected, stats.reused, stats.calls) == (2, 2, 0, 6)
    assert stats.failed_items == [] and not stats.stopped_by_budget
    loaded = cache.load()
    assert set(loaded) == {"i1", "i2"}
    record = loaded["i1"]
    assert record.small.content == "small-answer" and record.small.model == "small"
    assert (record.small.prompt_tokens, record.small.completion_tokens) == (10, 2)
    assert record.small.cost_usd == pytest.approx((10 * 1.0 + 2 * 2.0) / 1e6)
    assert record.frontier.cost_usd == pytest.approx((10 * 10.0 + 2 * 20.0) / 1e6)
    assert record.judge.choice == "easy" and record.judge.probabilities["easy"] == 0.9
    assert record.judge.cost_usd == pytest.approx(100 * 5.0 / 1e6)
    per_item = record.small.cost_usd + record.frontier.cost_usd + record.judge.cost_usd
    assert stats.spent_usd == pytest.approx(2 * per_item)  # both items cost the same here
    assert all(c.latency_ms >= 0 for c in (record.small, record.frontier, record.judge))


@pytest.mark.anyio
async def test_requests_use_the_prompt_zero_temperature_and_the_token_limit(cache):
    small = FakeModel("small")
    await collect([make_item(1, "hello?")], cache, **targets(small=small), max_tokens=32)
    [request] = small.calls
    assert request.messages[-1].content == "hello?"
    assert request.temperature == 0.0 and request.max_tokens == 32


@pytest.mark.anyio
async def test_rerun_reuses_the_cache_and_makes_no_calls(cache):
    items = [make_item(1), make_item(2)]
    first = targets()
    await collect(items, cache, **first, max_tokens=64)

    second = targets()
    stats = await collect(items, cache, **second, max_tokens=64)
    assert (stats.reused, stats.collected, stats.calls) == (2, 0, 0)
    assert second["small"].provider.calls == [] and second["judge"].provider.calls == 0
    assert pending_items(items, cache, **second, max_tokens=64) == []


@pytest.mark.anyio
@pytest.mark.parametrize(
    "change",
    [{"small_id": "s2"}, {"frontier_id": "f2"}, {"judge_id": "j2"}],
)
async def test_changing_a_model_identity_invalidates_the_cached_record(cache, change):
    items = [make_item(1)]
    await collect(items, cache, **targets(), max_tokens=64)
    assert len(pending_items(items, cache, **targets(**change), max_tokens=64)) == 1

    stats = await collect(items, cache, **targets(**change), max_tokens=64)
    assert stats.collected == 1 and stats.reused == 0


@pytest.mark.anyio
async def test_changing_the_prompt_or_token_limit_invalidates_the_record(cache):
    await collect([make_item(1, "old prompt")], cache, **targets(), max_tokens=64)
    assert pending_items([make_item(1, "new prompt")], cache, **targets(), max_tokens=64)
    assert pending_items([make_item(1, "old prompt")], cache, **targets(), max_tokens=128)
    assert not pending_items([make_item(1, "old prompt")], cache, **targets(), max_tokens=64)


@pytest.mark.anyio
async def test_a_failing_call_is_recorded_and_the_run_continues(cache):
    items = [make_item(1, "boom please"), make_item(2, "fine")]
    small = FakeModel("small", fail_on={"boom"})
    stats = await collect(items, cache, **targets(small=small), max_tokens=64)

    assert stats.collected == 2 and stats.failed_items == ["i1"]
    loaded = cache.load()
    assert "HTTP 500" in loaded["i1"].small.error and loaded["i1"].small.content == ""
    assert loaded["i1"].frontier.error is None  # the other calls still ran
    assert loaded["i2"].small.error is None


@pytest.mark.anyio
@pytest.mark.parametrize("judge", [FakeJudge(fail=True), FakeJudge(choice="medium")])
async def test_a_failing_or_invalid_judge_is_recorded_not_raised(cache, judge):
    stats = await collect([make_item(1)], cache, **targets(judge=judge), max_tokens=64)
    record = cache.load()["i1"]
    assert record.judge.error and record.judge.choice is None and record.judge.cost_usd == 0.0
    assert stats.failed_items == ["i1"]
    assert record.small.error is None  # models are still collected


@pytest.mark.anyio
async def test_budget_stops_before_starting_the_next_item_and_resumes_later(cache):
    items = [make_item(n) for n in range(1, 5)]
    per_item = (
        100 * 5.0 + (10 * 1.0 + 2 * 2.0) + (10 * 10.0 + 2 * 20.0)
    ) / 1e6  # judge + small + frontier

    stats = await collect(items, cache, **targets(), max_tokens=64, budget_usd=per_item * 1.5)
    assert stats.stopped_by_budget and stats.collected == 2  # stops once spend >= budget
    assert stats.spent_usd == pytest.approx(per_item * 2)
    assert len(cache.load()) == 2

    resumed = await collect(items, cache, **targets(), max_tokens=64)
    assert (resumed.reused, resumed.collected, resumed.stopped_by_budget) == (2, 2, False)
    assert len(cache.load()) == 4


@pytest.mark.anyio
async def test_zero_budget_makes_no_calls(cache):
    t = targets()
    stats = await collect([make_item(1)], cache, **t, max_tokens=64, budget_usd=0.0)
    assert stats.stopped_by_budget and stats.calls == 0
    assert t["small"].provider.calls == []


def test_estimate_counts_calls_and_bounds_cost_without_calling_anything():
    t = targets()
    items = [make_item(1, "a" * 40), make_item(2, "b" * 40)]
    est = estimate(items, **t, max_tokens=50)
    assert est.items == 2 and est.calls == 6
    assert est.max_output_tokens == 2 * 50 * 2
    assert est.cost_usd > 0
    assert t["small"].provider.calls == [] and t["judge"].provider.calls == 0


def test_estimate_scales_with_max_tokens_and_is_zero_for_free_models():
    items = [make_item(1)]
    paid = targets()
    free = {
        "small": ModelTarget(FakeModel("s"), "s", Price()),
        "frontier": ModelTarget(FakeModel("f"), "f", Price()),
        "judge": JudgeTarget(FakeJudge(), "j", Price()),
    }
    assert (
        estimate(items, **paid, max_tokens=200).cost_usd
        > estimate(items, **paid, max_tokens=20).cost_usd
    )
    assert estimate(items, **free, max_tokens=200).cost_usd == 0.0


def test_truncated_last_line_and_duplicate_records_are_handled(cache):
    good = CachedItem(
        item_id="a", key="k1", small=CallRecord(), frontier=CallRecord(), judge=JudgeCall()
    )
    newer = good.model_copy(update={"key": "k2"})
    cache.append(good)
    cache.append(newer)
    with open(cache.jsonl_path, "a", encoding="utf-8") as f:
        f.write('{"item_id": "b", "key": "tru')  # interrupted write, no newline
    loaded = cache.load()
    assert set(loaded) == {"a"} and loaded["a"].key == "k2"  # the later record wins


def test_cache_meta_round_trips_and_names_are_validated(tmp_path):
    cache = EvalCache(tmp_path, "run-1.v2")
    assert cache.read_meta() is None
    meta = CacheMeta(
        name="run-1.v2",
        created_at="2026-10-13T00:00:00+00:00",
        dataset="abc",
        small="s",
        frontier="f",
        judge="j",
        policy_version="v1",
        max_tokens=64,
        prices={"small": {"input": 1.0, "output": 2.0}},
    )
    cache.write_meta(meta)
    assert cache.read_meta() == meta
    for bad in ("../escape", "a/b", "", ".hidden", "x" * 80, "a b"):
        with pytest.raises(ValueError):
            EvalCache(tmp_path, bad)


def test_make_key_depends_on_every_input():
    t = targets()
    base = make_key(make_item(1), t["small"], t["frontier"], t["judge"], 64)
    assert base == make_key(make_item(1), t["small"], t["frontier"], t["judge"], 64)
    assert base != make_key(make_item(1, "other"), t["small"], t["frontier"], t["judge"], 64)
    assert base != make_key(make_item(1), t["small"], t["frontier"], t["judge"], 65)
