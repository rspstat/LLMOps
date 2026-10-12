import csv
import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from evals.cache import CachedItem, CacheMeta
from evals.collect import key_from_parts
from evals.metrics import (
    ConfigSummary,
    GroupAccuracy,
    JudgeQuality,
    accuracy_by,
    judge_quality,
    summarize,
    with_baseline,
)
from evals.replay import default_configs, replay, score_cached, usable_items
from evals.schema import EvalItem
from evals.scorers import Scorer


@dataclass(slots=True)
class ReportData:
    name: str
    meta: CacheMeta | None
    dataset_changed: bool
    labels_reviewed: bool | None
    n_items: int
    n_usable: int
    excluded: list[tuple[str, str]]
    empty_answers: dict[str, int]  # model -> number of usable items it answered with nothing
    taus: list[float]
    summaries: list[ConfigSummary]
    quality: list[JudgeQuality]
    by_difficulty: list[GroupAccuracy]
    by_category: list[GroupAccuracy]
    by_lang: list[GroupAccuracy]

    @property
    def mock_parts(self) -> list[str]:
        """Which components were offline mocks when this cache was collected."""
        if self.meta is None:
            return []
        parts = {
            "소형 모델": self.meta.small,
            "상용 모델": self.meta.frontier,
            "판정기": self.meta.judge,
        }
        return [name for name, identity in parts.items() if identity.startswith("mock")]

    @property
    def uses_mock(self) -> bool:
        return bool(self.mock_parts)


def drop_stale(
    items: Sequence[EvalItem], cached: Mapping[str, CachedItem], meta: CacheMeta | None
) -> tuple[dict[str, CachedItem], list[str]]:
    """Keep only records collected under the configuration the metadata describes.

    A cache can mix runs (a different model for some items, or an edited prompt). Reporting such
    a mix as one configuration would be wrong, so those records are set aside and listed.
    """
    if meta is None:
        return dict(cached), []
    fresh: dict[str, CachedItem] = {}
    stale: list[str] = []
    for item in items:
        record = cached.get(item.id)
        if record is None:
            continue
        expected = key_from_parts(
            item, meta.small, meta.frontier, meta.judge, meta.policy_version, meta.max_tokens
        )
        if record.key == expected:
            fresh[item.id] = record
        else:
            stale.append(item.id)
    return fresh, stale


async def build_report_data(
    name: str,
    items: Sequence[EvalItem],
    cached: Mapping[str, CachedItem],
    scorer: Scorer,
    taus: Sequence[float],
    *,
    meta: CacheMeta | None = None,
    dataset_changed: bool = False,
    labels_reviewed: bool | None = None,
) -> ReportData:
    cached, stale = drop_stale(items, cached, meta)
    usable = usable_items(items, cached)
    # Stale ids are absent from `cached` now, so `usable_items` called them "not collected";
    # the more precise reason replaces that rather than listing the item twice.
    excluded = dict(usable.excluded)
    for item_id in stale:
        excluded[item_id] = "stale record: different model, prompt or settings"
    summaries = []
    for spec in default_configs(taus):
        summaries.append(summarize(spec, await replay(usable.items, cached, spec, scorer)))
    scores = score_cached(usable.items, cached, scorer)
    quality = [
        judge_quality(usable.items, cached, scores, tau, source)
        for tau in taus
        for source in ("author", "measured")
    ]
    return ReportData(
        name=name,
        meta=meta,
        dataset_changed=dataset_changed,
        labels_reviewed=labels_reviewed,
        n_items=len(items),
        n_usable=len(usable.items),
        excluded=list(excluded.items()),
        empty_answers={
            name: count
            for name, count in (
                ("소형 모델", sum(cached[i.id].small.empty for i in usable.items)),
                ("상용 모델", sum(cached[i.id].frontier.empty for i in usable.items)),
            )
            if count
        },
        taus=list(taus),
        summaries=with_baseline(summaries),
        quality=quality,
        by_difficulty=accuracy_by(usable.items, scores, lambda i: i.difficulty),
        by_category=accuracy_by(usable.items, scores, lambda i: i.category),
        by_lang=accuracy_by(usable.items, scores, lambda i: i.lang),
    )


def _pct(x: float | None, digits: int = 1) -> str:
    return "-" if x is None else f"{100 * x:.{digits}f}%"


def _signed_pct(x: float | None) -> str:
    return "-" if x is None else f"{100 * x:+.1f}%p"


def _usd(x: float) -> str:
    return f"${x:.4f}"


def _config_table(summaries: Sequence[ConfigSummary]) -> list[str]:
    lines = [
        "| 설정 | 정확도 (95% 구간) | 비용/1k요청 | 절감률 | 정확도 변화 | 지연 p50/p95 (ms) "
        "| 상용 비율 | 판정 호출 | 승격 | 낭비¹ | 위험² |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for s in summaries:
        accuracy = (
            f"{_pct(s.accuracy)} ({_pct(s.ci_low, 0)}–{_pct(s.ci_high, 0)})"
            if s.accuracy is not None
            else "-"
        )
        failure = "" if not s.judge_failure_rate else f", 실패 {_pct(s.judge_failure_rate, 0)}"
        lines.append(
            f"| `{s.name}` | {accuracy} | {_usd(s.cost_per_1k)} | {_pct(s.cost_saving_vs_frontier)} "
            f"| {_signed_pct(s.accuracy_delta_vs_frontier)} | {s.latency_p50:.0f} / {s.latency_p95:.0f} "
            f"| {_pct(s.frontier_rate, 0)} | {_pct(s.judge_call_rate, 0)}{failure} "
            f"| {_pct(s.promotion_rate, 0)} | {s.wasted_frontier} | {s.risky_small} |"
        )
    return lines


def _group_table(title: str, rows: Sequence[GroupAccuracy]) -> list[str]:
    lines = [f"**{title}**", "", "| 그룹 | n | 소형 모델 | 상용 모델 |", "|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r.group} | {r.n_scored}/{r.n} | {_pct(r.small)} | {_pct(r.frontier)} |")
    return lines + [""]


def render_markdown(data: ReportData) -> str:
    out: list[str] = [f"# 라우팅 평가 리포트 · {data.name}", ""]

    warnings = []
    if data.mock_parts == ["판정기"]:
        # The model answers are real, so accuracy / cost / latency of the baselines are valid;
        # only what depends on the judge is not.
        warnings.append(
            "**판정기가 mock입니다.** `hybrid@τ`·`judge_only@τ` 행, 판정 호출 비용·지연, "
            "'판정기 품질' 표는 의미가 없습니다. 소형·상용 모델의 정확도·비용·지연과 "
            "`all_small`·`all_frontier`·`rules` 행은 실제 측정값입니다."
        )
    elif data.uses_mock:
        warnings.append(
            f"**mock provider({', '.join(data.mock_parts)})로 수집한 결과입니다.** 모델 응답이 "
            "가짜(echo)라서 정확도·비용·지연은 의미가 없고, 이 리포트는 파이프라인이 동작하는지만 보여 줍니다."
        )
    if data.labels_reviewed is False:
        warnings.append(
            "데이터셋의 난이도 라벨이 **검토 전 AI 초안**입니다 (`낭비`·`위험`·작성자 라벨 기준 지표에 영향)."
        )
    if data.empty_answers:
        counts = ", ".join(f"{name} {count}건" for name, count in data.empty_answers.items())
        warnings.append(
            f"**빈 응답이 있습니다 ({counts}).** 추론 모델이 `max_tokens`를 생각에 다 써서 답을 못 낸 "
            "경우가 흔하며, 오답으로 채점되어 모델이 실제보다 약해 보입니다. "
            "추론 기능이 없는 채팅 모델을 쓰거나 `--max-tokens`를 늘려 다시 수집하세요."
        )
    if data.dataset_changed:
        warnings.append(
            "수집 이후 **데이터셋 파일이 바뀌었습니다.** 캐시된 응답이 현재 프롬프트와 다를 수 있으니 다시 수집하세요."
        )
    if data.n_usable < 200:
        warnings.append(
            f"표본이 작습니다 (n={data.n_usable}). 95% 구간이 넓어서 설정 간 차이는 구간이 겹치면 "
            "구분되지 않는 것으로 보세요."
        )
    out += [f"> ⚠ {w}" for w in warnings] + ([""] if warnings else [])

    out += ["## 실행 정보", ""]
    out.append(f"- 사용 항목: {data.n_usable} / {data.n_items}")
    if data.excluded:
        out.append("- 제외: " + ", ".join(f"`{i}` ({why})" for i, why in data.excluded))
    if data.meta:
        m = data.meta
        out += [
            f"- 소형 모델: `{m.small}` · 상용 모델: `{m.frontier}` · 판정기: `{m.judge}`",
            f"- 판정 정책: `{m.policy_version}` · max_tokens: {m.max_tokens} · 수집 시각: {m.created_at}",
            "- 단가(USD/100만 토큰): "
            + ", ".join(
                f"{k} 입력 {v['input']:g} / 출력 {v['output']:g}" for k, v in m.prices.items()
            ),
        ]
    else:
        out.append("- 수집 메타데이터가 없습니다.")
    out.append("")

    out += ["## 1. 설정별 비교", ""] + _config_table(data.summaries) + [""]
    out += [
        "¹ 낭비: 작성자 라벨이 easy인데 상용 모델로 보낸 항목 수 · ² 위험: 작성자 라벨이 hard인데 소형 모델로 보낸 항목 수. "
        "절감률·정확도 변화는 `all_frontier` 대비입니다. `hybrid@τ`는 규칙에 걸리면 판정 없이 확정, "
        "`judge_only@τ`는 항상 판정기에 묻습니다.",
        "",
        '## 2. 판정기 품질 ("easy"를 양성으로 본 정밀도·재현율)',
        "",
        "| τ | 기준 라벨 | n (제외) | 정밀도 | 재현율 | TP / FP / FN / TN |",
        "|---|---|---|---|---|---|",
    ]
    names = {"author": "작성자 라벨", "measured": "실측(소형 모델 정답)"}
    for q in data.quality:
        out.append(
            f"| {q.tau:g} | {names[q.label_source]} | {q.n} ({q.excluded}) | {_pct(q.precision)} "
            f"| {_pct(q.recall)} | {q.tp} / {q.fp} / {q.fn} / {q.tn} |"
        )
    out += [
        "",
        '정밀도가 낮다 = 판정기가 "쉽다"고 한 요청 중 실제로는 어려운 것이 많다 (소형 모델 오답 위험). '
        "재현율이 낮다 = 쉬운 요청을 놓쳐 상용 모델로 보낸다 (비용 낭비).",
        "",
        "## 3. 모델 단독 정확도 (라우팅 없이)",
        "",
    ]
    out += _group_table("작성자 난이도 라벨별", data.by_difficulty)
    out += _group_table("범주별", data.by_category)
    out += _group_table("언어별", data.by_lang)
    out += [
        "작성자 라벨이 맞다면 easy 그룹에서 소형 모델이 상용 모델과 비슷하고 hard 그룹에서 차이가 커야 합니다.",
        "",
        "## 해석할 때 주의",
        "",
        "- 이 숫자는 **캐시된 응답을 재생한 근사**입니다. 설정마다 모델을 다시 부르지 않았으므로 항목당 모델 응답·지연은 "
        "한 번 측정한 값입니다 (지연은 분산이 큽니다).",
        "- 판정기 호출의 비용·지연은 수집 때 기록한 값을 판정기를 부른 항목에만 더했습니다.",
        "- 정확도는 규칙 채점이 가능한 문항(짧은 정답)만 대상입니다. 긴 생성·창작 요청의 품질은 측정하지 않았습니다.",
        "- Jev의 속도·비용 수치는 회사 발표값이며, 여기의 값은 이 실행에서 측정한 것만 해당합니다.",
        "",
    ]
    return "\n".join(out)


def write_report(data: ReportData, out_dir: str | Path) -> list[Path]:
    directory = Path(out_dir) / data.name
    directory.mkdir(parents=True, exist_ok=True)

    report = directory / "report.md"
    report.write_text(render_markdown(data), encoding="utf-8", newline="\n")

    def write_csv(path: Path, rows: Sequence[object]) -> None:
        dicts = [asdict(r) for r in rows]  # type: ignore[arg-type]
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(dicts[0]) if dicts else [])
            writer.writeheader()
            writer.writerows(dicts)

    configs_csv = directory / "configs.csv"
    quality_csv = directory / "judge_quality.csv"
    write_csv(configs_csv, data.summaries)
    write_csv(quality_csv, data.quality)

    summary = directory / "summary.json"
    summary.write_text(
        json.dumps(
            {
                "name": data.name,
                "uses_mock": data.uses_mock,
                "mock_parts": data.mock_parts,
                "labels_reviewed": data.labels_reviewed,
                "n_items": data.n_items,
                "n_usable": data.n_usable,
                "excluded": data.excluded,
                "configs": [asdict(s) for s in data.summaries],
                "judge_quality": [asdict(q) for q in data.quality],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return [report, configs_csv, quality_csv, summary]
