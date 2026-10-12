import pytest

from evals.cache import CachedItem, CallRecord, EvalCache, JudgeCall
from evals.collect import JudgeTarget, ModelTarget, collect
from evals.replay import ConfigSpec, default_configs, replay, score_cached, usable_items
from evals.schema import EvalItem, load_items
from evals.scorers import RuleScorer
from gateway.pipeline import Price
from providers.mock import MockProvider
from providers.mock_decision import MockDecisionProvider
from router.hybrid_router import HybridRouter
from router.rule_router import RuleRouter

SCORER = RuleScorer()
SMALL_COST, FRONTIER_COST, JUDGE_COST = 0.001, 0.010, 0.0005
SMALL_MS, FRONTIER_MS, JUDGE_MS = 100, 500, 200


def make_item(item_id: str, difficulty: str, prompt: str) -> EvalItem:
    return EvalItem(
        id=item_id,
        prompt=prompt,
        lang="en",
        category="math",
        difficulty=difficulty,
        answer_type="exact",
        reference=["ok"],
    )


def make_cached(item_id: str, *, small_ok: bool, p_easy: float | None) -> CachedItem:
    if p_easy is None:
        judge = JudgeCall(error="judge: HTTP 500", latency_ms=JUDGE_MS)
    else:
        judge = JudgeCall(
            choice="easy" if p_easy >= 0.5 else "hard",
            probabilities={"easy": p_easy, "hard": round(1 - p_easy, 4)},
            confidence=max(p_easy, 1 - p_easy),
            model="judge-1",
            input_tokens=100,
            output_tokens=1,
            latency_ms=JUDGE_MS,
            cost_usd=JUDGE_COST,
        )
    return CachedItem(
        item_id=item_id,
        key="k",
        small=CallRecord(
            content="ok" if small_ok else "no", model="s", latency_ms=SMALL_MS, cost_usd=SMALL_COST
        ),
        frontier=CallRecord(
            content="ok", model="f", latency_ms=FRONTIER_MS, cost_usd=FRONTIER_COST
        ),
        judge=judge,
    )


# id, author label, prompt, small model right?, judge p(easy)
ROWS = [
    ("A", "easy", "plain A", True, 0.95),
    ("B", "easy", "plain B", True, 0.75),
    ("C", "easy", "plain C", True, 0.60),  # judge leans easy but is unsure
    ("D", "hard", "plain D", False, 0.20),
    ("E", "hard", "plain E", False, 0.80),  # judge is confidently wrong
    ("F", "hard", "please analyze F", False, 0.10),  # keyword rule fires
]
ITEMS = [make_item(i, d, p) for i, d, p, _, _ in ROWS]
CACHED = {i: make_cached(i, small_ok=ok, p_easy=p) for i, _, _, ok, p in ROWS}


async def run(mode: str, tau: float | None = None, cached=None):
    spec = ConfigSpec(f"{mode}@{tau}", mode, tau)
    outcomes = await replay(ITEMS, cached or CACHED, spec, SCORER)
    return {o.item_id: o for o in outcomes}


def routes(outcomes) -> dict[str, str]:
    return {i: o.route for i, o in outcomes.items()}


@pytest.mark.anyio
async def test_fixed_configs_use_one_model_for_everything():
    small = await run("all_small")
    frontier = await run("all_frontier")
    assert set(routes(small).values()) == {"small"} and {o.reason for o in small.values()} == {
        "fixed"
    }
    assert sum(o.correct for o in small.values()) == 3  # A, B, C
    assert sum(o.cost_usd for o in small.values()) == pytest.approx(6 * SMALL_COST)
    assert set(routes(frontier).values()) == {"frontier"}
    assert all(o.correct for o in frontier.values())
    assert not any(o.judge_consulted for o in [*small.values(), *frontier.values()])


@pytest.mark.anyio
async def test_rules_mode_only_catches_the_keyword_item():
    out = await run("rules")
    assert routes(out) == {
        "A": "small",
        "B": "small",
        "C": "small",
        "D": "small",
        "E": "small",
        "F": "frontier",
    }
    assert out["F"].reason == "keyword:analyze"
    assert sum(o.correct for o in out.values()) == 4  # A, B, C and F (answered by the frontier)
    assert sum(o.cost_usd for o in out.values()) == pytest.approx(5 * SMALL_COST + FRONTIER_COST)
    assert not any(o.judge_consulted for o in out.values())


@pytest.mark.anyio
async def test_hybrid_promotes_unsure_and_hard_items_and_skips_the_judge_on_rule_hits():
    out = await run("hybrid", 0.7)
    assert routes(out) == {
        "A": "small",
        "B": "small",
        "C": "frontier",
        "D": "frontier",
        "E": "small",
        "F": "frontier",
    }
    assert {i: o.reason for i, o in out.items()} == {
        "A": "judge_easy",
        "B": "judge_easy",
        "C": "promoted_low_confidence",
        "D": "judge_hard",
        "E": "judge_easy",
        "F": "keyword:analyze",
    }
    assert out["F"].judge_consulted is False
    assert all(out[i].judge_consulted for i in "ABCDE")
    assert out["A"].p_easy == 0.95 and out["F"].p_easy is None
    assert sum(o.correct for o in out.values()) == 5  # only E (small, wrong) fails
    assert sum(o.cost_usd for o in out.values()) == pytest.approx(
        3 * SMALL_COST + 3 * FRONTIER_COST + 5 * JUDGE_COST
    )
    assert out["A"].latency_ms == SMALL_MS + JUDGE_MS  # judge latency comes from the recording
    assert out["C"].latency_ms == FRONTIER_MS + JUDGE_MS
    assert out["F"].latency_ms == FRONTIER_MS


@pytest.mark.anyio
async def test_higher_threshold_sends_more_traffic_to_the_frontier():
    out = await run("hybrid", 0.9)
    assert [i for i, r in routes(out).items() if r == "small"] == ["A"]
    assert all(o.correct for o in out.values())


@pytest.mark.anyio
async def test_judge_only_asks_the_judge_even_for_keyword_items():
    out = await run("judge_only", 0.7)
    assert out["F"].judge_consulted and out["F"].reason == "judge_hard"
    assert sum(o.judge_consulted for o in out.values()) == 6


@pytest.mark.anyio
async def test_a_recorded_judge_failure_falls_back_to_rules_and_is_charged_its_latency_only():
    cached = {**CACHED, "C": make_cached("C", small_ok=True, p_easy=None)}
    out = await run("hybrid", 0.7, cached)
    c = out["C"]
    assert c.judge_consulted and c.judge_failed
    assert c.route == "small" and c.reason == "judge_unavailable"  # what the rules say
    assert c.cost_usd == pytest.approx(SMALL_COST)  # a failed judge call costs nothing
    assert c.latency_ms == SMALL_MS + JUDGE_MS  # but the wait still happened


@pytest.mark.anyio
async def test_threshold_modes_require_a_threshold():
    with pytest.raises(ValueError, match="threshold"):
        await replay(ITEMS, CACHED, ConfigSpec("bad", "hybrid", None), SCORER)


def test_default_configs_cover_baselines_and_both_sweeps():
    specs = default_configs([0.5, 0.7])
    assert [s.name for s in specs] == [
        "all_small",
        "all_frontier",
        "rules",
        "hybrid@0.5",
        "hybrid@0.7",
        "judge_only@0.5",
        "judge_only@0.7",
    ]
    assert specs[4].mode == "hybrid" and specs[4].tau == 0.7


def test_usable_items_excludes_missing_and_failed_model_calls_but_keeps_judge_failures():
    cached = dict(CACHED)
    del cached["A"]
    cached["B"] = cached["B"].model_copy(update={"small": CallRecord(error="HTTP 500")})
    cached["C"] = cached["C"].model_copy(update={"frontier": CallRecord(error="HTTP 500")})
    cached["D"] = make_cached("D", small_ok=False, p_easy=None)  # judge outage is still usable
    result = usable_items(ITEMS, cached)
    assert [i.id for i in result.items] == ["D", "E", "F"]
    assert dict(result.excluded) == {
        "A": "not collected",
        "B": "small model call failed",
        "C": "frontier model call failed",
    }


def test_score_cached_scores_both_models():
    scores = score_cached(ITEMS, CACHED, SCORER)
    assert scores["A"].small is True and scores["D"].small is False
    assert all(s.frontier is True for s in scores.values())


@pytest.mark.anyio
async def test_replay_makes_the_same_routing_decisions_as_running_the_router_live(tmp_path):
    # Collect the real dataset with the offline mocks, replay it, and compare against the
    # gateway's own router being asked directly: replay must not re-implement routing.
    items = load_items("evals/datasets/routing_v1.jsonl")
    cache = EvalCache(tmp_path, "mock")
    await collect(
        items,
        cache,
        small=ModelTarget(MockProvider("mock-small"), "mock:small", Price()),
        frontier=ModelTarget(MockProvider("mock-frontier"), "mock:frontier", Price()),
        judge=JudgeTarget(MockDecisionProvider(), "mock:judge", Price()),
        max_tokens=64,
    )
    cached = cache.load()
    live = HybridRouter(RuleRouter(), MockDecisionProvider())
    for tau in (0.5, 0.7, 0.9):
        live.config = type(live.config)(promote_threshold=tau)
        replayed = await replay(items, cached, ConfigSpec(f"h{tau}", "hybrid", tau), SCORER)
        for item, outcome in zip(items, replayed, strict=True):
            decision = await live.route(item.prompt)
            assert (outcome.route, outcome.reason) == (decision.route.value, decision.reason), (
                item.id
            )
            if decision.judge is not None:
                assert outcome.p_easy == pytest.approx(decision.detail["p_easy"])
