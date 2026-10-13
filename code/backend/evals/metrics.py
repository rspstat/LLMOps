import math
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Literal

from evals.cache import CachedItem
from evals.replay import ConfigSpec, ItemOutcome, ModelScores
from evals.schema import EvalItem

_Z95 = 1.959964


def wilson_interval(successes: int, n: int, z: float = _Z95) -> tuple[float, float]:
    """Wilson score interval for a proportion; (0, 1) when there are no observations."""
    if n == 0:
        return 0.0, 1.0
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def percentile(values: Sequence[float], q: float) -> float:
    """Nearest-rank percentile (q in 0-100); 0.0 for no data."""
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(1, math.ceil(q / 100 * len(ordered)))
    return ordered[rank - 1]


@dataclass(frozen=True, slots=True)
class ConfigSummary:
    name: str
    mode: str
    tau: float | None
    n: int
    n_scored: int
    n_correct: int
    accuracy: float | None
    ci_low: float | None
    ci_high: float | None
    cost_total: float
    cost_per_1k: float
    latency_p50: float
    latency_p95: float
    frontier_rate: float
    judge_call_rate: float
    judge_failure_rate: float | None  # failed / consulted; None when the judge was never asked
    promotion_rate: float
    wasted_frontier: int  # author-labelled easy, sent to the frontier model
    risky_small: int  # author-labelled hard, sent to the small model
    cost_saving_vs_frontier: float | None = None
    accuracy_delta_vs_frontier: float | None = None


def summarize(spec: ConfigSpec, outcomes: Sequence[ItemOutcome]) -> ConfigSummary:
    n = len(outcomes)
    scored = [o for o in outcomes if o.correct is not None]
    correct = sum(1 for o in scored if o.correct)
    consulted = [o for o in outcomes if o.judge_consulted]
    cost_total = sum(o.cost_usd for o in outcomes)
    latencies = [float(o.latency_ms) for o in outcomes]
    low, high = wilson_interval(correct, len(scored)) if scored else (None, None)

    def rate(count: int) -> float:
        return count / n if n else 0.0

    return ConfigSummary(
        name=spec.name,
        mode=spec.mode,
        tau=spec.tau,
        n=n,
        n_scored=len(scored),
        n_correct=correct,
        accuracy=correct / len(scored) if scored else None,
        ci_low=low,
        ci_high=high,
        cost_total=cost_total,
        cost_per_1k=1000 * cost_total / n if n else 0.0,
        latency_p50=percentile(latencies, 50),
        latency_p95=percentile(latencies, 95),
        frontier_rate=rate(sum(1 for o in outcomes if o.route == "frontier")),
        judge_call_rate=rate(len(consulted)),
        judge_failure_rate=(
            sum(1 for o in consulted if o.judge_failed) / len(consulted) if consulted else None
        ),
        promotion_rate=rate(sum(1 for o in outcomes if o.reason == "promoted_low_confidence")),
        wasted_frontier=sum(
            1 for o in outcomes if o.difficulty == "easy" and o.route == "frontier"
        ),
        risky_small=sum(1 for o in outcomes if o.difficulty == "hard" and o.route == "small"),
    )


def with_baseline(
    summaries: Sequence[ConfigSummary], baseline_name: str = "all_frontier"
) -> list[ConfigSummary]:
    """Add cost saving and accuracy change relative to always using the frontier model."""
    baseline = next((s for s in summaries if s.name == baseline_name), None)
    if baseline is None:
        return list(summaries)
    result = []
    for s in summaries:
        saving = 1 - s.cost_total / baseline.cost_total if baseline.cost_total > 0 else None
        delta = (
            s.accuracy - baseline.accuracy
            if s.accuracy is not None and baseline.accuracy is not None
            else None
        )
        result.append(replace(s, cost_saving_vs_frontier=saving, accuracy_delta_vs_frontier=delta))
    return result


@dataclass(frozen=True, slots=True)
class JudgeQuality:
    """How well "judge says easy with p(easy) >= tau" predicts a label. Positive = easy."""

    tau: float
    label_source: Literal["author", "measured"]
    n: int
    excluded: int
    tp: int
    fp: int
    fn: int
    tn: int
    precision: float | None
    recall: float | None


def judge_quality(
    items: Sequence[EvalItem],
    cached: Mapping[str, CachedItem],
    scores: Mapping[str, ModelScores],
    tau: float,
    label_source: Literal["author", "measured"],
) -> JudgeQuality:
    """`author` labels come from the dataset; `measured` means the small model answered correctly.

    Items whose judge call failed are excluded, and so are unscorable items for `measured`.
    """
    tp = fp = fn = tn = excluded = 0
    for item in items:
        call = cached[item.id].judge
        if call.error is not None or call.choice is None:
            excluded += 1
            continue
        if label_source == "author":
            truth = item.difficulty == "easy"
        else:
            small = scores[item.id].small
            if small is None:
                excluded += 1
                continue
            truth = small
        predicted = call.choice == "easy" and call.probabilities.get("easy", 0.0) >= tau
        if predicted and truth:
            tp += 1
        elif predicted:
            fp += 1
        elif truth:
            fn += 1
        else:
            tn += 1
    return JudgeQuality(
        tau=tau,
        label_source=label_source,
        n=tp + fp + fn + tn,
        excluded=excluded,
        tp=tp,
        fp=fp,
        fn=fn,
        tn=tn,
        precision=tp / (tp + fp) if tp + fp else None,
        recall=tp / (tp + fn) if tp + fn else None,
    )


@dataclass(frozen=True, slots=True)
class GroupAccuracy:
    group: str
    n: int
    n_scored: int
    small: float | None
    frontier: float | None


def accuracy_by(
    items: Sequence[EvalItem],
    scores: Mapping[str, ModelScores],
    key: Callable[[EvalItem], str],
) -> list[GroupAccuracy]:
    """Stand-alone accuracy of each model per group (e.g. per author difficulty label)."""
    groups: dict[str, list[EvalItem]] = defaultdict(list)
    for item in items:
        groups[key(item)].append(item)
    rows = []
    for name in sorted(groups):
        members = groups[name]
        scored = [i for i in members if scores[i.id].small is not None]
        rows.append(
            GroupAccuracy(
                group=name,
                n=len(members),
                n_scored=len(scored),
                small=(sum(1 for i in scored if scores[i.id].small) / len(scored))
                if scored
                else None,
                frontier=(
                    sum(1 for i in scored if scores[i.id].frontier) / len(scored)
                    if scored
                    else None
                ),
            )
        )
    return rows
