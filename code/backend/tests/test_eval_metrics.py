import pytest

from evals.metrics import (
    accuracy_by,
    judge_quality,
    percentile,
    summarize,
    wilson_interval,
    with_baseline,
)
from evals.replay import ConfigSpec, ItemOutcome, replay, score_cached
from evals.scorers import RuleScorer
from tests.test_eval_replay import CACHED, ITEMS, make_cached

SCORER = RuleScorer()


def test_wilson_interval_matches_hand_calculation():
    low, high = wilson_interval(8, 10)
    assert low == pytest.approx(0.4902, abs=1e-3) and high == pytest.approx(0.9433, abs=1e-3)
    low, high = wilson_interval(10, 10)
    assert low == pytest.approx(0.7225, abs=1e-3) and high == pytest.approx(1.0, abs=1e-9)
    assert wilson_interval(0, 0) == (0.0, 1.0)
    low, high = wilson_interval(0, 10)
    assert low == 0.0 and high == pytest.approx(0.2775, abs=1e-3)


def test_percentile_is_nearest_rank():
    values = [40.0, 10.0, 30.0, 20.0]
    assert percentile(values, 50) == 20.0
    assert percentile(values, 95) == 40.0
    assert percentile(values, 0) == 10.0
    assert percentile([7.0], 95) == 7.0
    assert percentile([], 50) == 0.0


async def summaries(taus=(0.7,)):
    from evals.replay import default_configs

    result = []
    for spec in default_configs(taus):
        result.append(summarize(spec, await replay(ITEMS, CACHED, spec, SCORER)))
    return with_baseline(result)


@pytest.mark.anyio
async def test_hybrid_summary_matches_hand_computed_numbers():
    by_name = {s.name: s for s in await summaries()}
    s = by_name["hybrid@0.7"]
    assert (s.n, s.n_scored, s.n_correct) == (6, 6, 5)
    assert s.accuracy == pytest.approx(5 / 6)
    assert s.ci_low < s.accuracy < s.ci_high
    assert s.cost_total == pytest.approx(0.0355)
    assert s.cost_per_1k == pytest.approx(1000 * 0.0355 / 6)
    assert (s.latency_p50, s.latency_p95) == (300.0, 700.0)  # 300,300,300,500,700,700
    assert s.frontier_rate == pytest.approx(3 / 6)
    assert s.judge_call_rate == pytest.approx(5 / 6) and s.judge_failure_rate == 0.0
    assert s.promotion_rate == pytest.approx(1 / 6)  # C
    assert s.wasted_frontier == 1  # C: easy, sent to the frontier
    assert s.risky_small == 1  # E: hard, sent to the small model
    assert s.cost_saving_vs_frontier == pytest.approx(1 - 0.0355 / 0.06)
    assert s.accuracy_delta_vs_frontier == pytest.approx(5 / 6 - 1)


@pytest.mark.anyio
async def test_baseline_rows_bound_the_trade_off():
    by_name = {s.name: s for s in await summaries()}
    frontier, small, rules = by_name["all_frontier"], by_name["all_small"], by_name["rules"]
    assert frontier.accuracy == 1.0 and frontier.cost_saving_vs_frontier == pytest.approx(0.0)
    assert small.accuracy == 0.5 and small.cost_saving_vs_frontier == pytest.approx(0.9)
    assert small.risky_small == 3 and small.wasted_frontier == 0
    assert rules.accuracy == pytest.approx(4 / 6) and rules.judge_call_rate == 0.0
    assert rules.judge_failure_rate is None  # never asked


@pytest.mark.anyio
async def test_summary_without_scorable_items_has_no_accuracy():
    outcome = ItemOutcome(
        "x", "en", "math", "easy", "small", "fixed", None, 0.0, 0, False, False, None
    )
    s = summarize(ConfigSpec("all_small", "all_small"), [outcome])
    assert s.accuracy is None and s.ci_low is None and s.n_scored == 0
    empty = summarize(ConfigSpec("all_small", "all_small"), [])
    assert empty.n == 0 and empty.cost_per_1k == 0.0 and empty.frontier_rate == 0.0


def test_with_baseline_is_a_noop_without_a_frontier_row():
    s = summarize(ConfigSpec("all_small", "all_small"), [])
    assert with_baseline([s])[0].cost_saving_vs_frontier is None


def test_judge_quality_counts_a_confusion_matrix_for_both_label_sources():
    scores = score_cached(ITEMS, CACHED, SCORER)
    for source in ("author", "measured"):  # here the two labels happen to agree
        q = judge_quality(ITEMS, CACHED, scores, 0.7, source)
        assert (q.tp, q.fp, q.fn, q.tn) == (
            2,
            1,
            1,
            2,
        )  # predicted easy: A, B, E; truly easy: A, B, C
        assert q.n == 6 and q.excluded == 0
        assert q.precision == pytest.approx(2 / 3) and q.recall == pytest.approx(2 / 3)
    strict = judge_quality(ITEMS, CACHED, scores, 0.9, "author")
    assert (strict.tp, strict.fp, strict.fn, strict.tn) == (1, 0, 2, 3)
    assert strict.precision == 1.0 and strict.recall == pytest.approx(1 / 3)


def test_judge_quality_excludes_failed_judge_calls_and_handles_empty_denominators():
    cached = {**CACHED, "A": make_cached("A", small_ok=True, p_easy=None)}
    scores = score_cached(ITEMS, cached, SCORER)
    q = judge_quality(ITEMS, cached, scores, 0.7, "author")
    assert q.excluded == 1 and q.n == 5
    nothing_easy = judge_quality(ITEMS, CACHED, scores, 1.01, "author")
    assert nothing_easy.tp == nothing_easy.fp == 0 and nothing_easy.precision is None


def test_measured_labels_can_disagree_with_author_labels():
    # D is author-hard but the small model happens to get it right: a measured-easy item.
    cached = {**CACHED, "D": make_cached("D", small_ok=True, p_easy=0.2)}
    scores = score_cached(ITEMS, cached, SCORER)
    author = judge_quality(ITEMS, cached, scores, 0.7, "author")
    measured = judge_quality(ITEMS, cached, scores, 0.7, "measured")
    assert author.fn == 1 and measured.fn == 2  # D now counts as an easy item the judge missed


def test_accuracy_by_group_shows_whether_author_labels_match_reality():
    scores = score_cached(ITEMS, CACHED, SCORER)
    rows = {r.group: r for r in accuracy_by(ITEMS, scores, lambda i: i.difficulty)}
    assert rows["easy"].small == 1.0 and rows["easy"].frontier == 1.0 and rows["easy"].n == 3
    assert rows["hard"].small == 0.0 and rows["hard"].frontier == 1.0
