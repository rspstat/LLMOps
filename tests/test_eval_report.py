import csv
import json

import pytest

from evals.cache import CacheMeta
from evals.collect import key_from_parts
from evals.replay import default_configs
from evals.report import build_report_data, render_markdown, write_report
from evals.scorers import RuleScorer
from tests.test_eval_replay import CACHED, ITEMS

TAUS = [0.5, 0.7, 0.9]


def make_meta(small="slm:tiny", frontier="openai:big", judge="jev:j", max_tokens=64) -> CacheMeta:
    return CacheMeta(
        name="r",
        created_at="2026-10-13T00:00:00+00:00",
        dataset="abc",
        small=small,
        frontier=frontier,
        judge=judge,
        policy_version="v1",
        max_tokens=max_tokens,
        prices={"small": {"input": 0.1, "output": 0.2}, "frontier": {"input": 3.0, "output": 15.0}},
    )


def keyed(meta: CacheMeta, cached=CACHED):
    """The fixture records, stamped with the key the metadata would produce."""
    return {
        item.id: cached[item.id].model_copy(
            update={
                "key": key_from_parts(
                    item,
                    meta.small,
                    meta.frontier,
                    meta.judge,
                    meta.policy_version,
                    meta.max_tokens,
                )
            }
        )
        for item in ITEMS
    }


async def build(meta=None, cached=None, **kwargs):
    meta = meta or make_meta()
    return await build_report_data(
        "r", ITEMS, cached or keyed(meta), RuleScorer(), TAUS, meta=meta, **kwargs
    )


@pytest.mark.anyio
async def test_report_contains_every_config_and_the_hand_computed_headline_numbers():
    text = render_markdown(await build())
    for spec in default_configs(TAUS):
        assert f"`{spec.name}`" in text
    row = next(line for line in text.splitlines() if line.startswith("| `hybrid@0.7`"))
    assert "83.3%" in row  # 5 of 6 correct
    assert "$5.9167" in row  # 1000 * 0.0355 / 6
    assert "300 / 700" in row  # p50 / p95 latency
    assert "40.8%" in row  # cost saving against all_frontier
    assert "-16.7%p" in row  # accuracy change against all_frontier
    assert "66.7%" in text  # judge precision and recall at tau 0.7
    assert "`slm:tiny`" in text and "`jev:j`" in text


@pytest.mark.anyio
async def test_mock_runs_are_flagged_at_the_top_and_real_runs_are_not():
    mock_meta = make_meta(small="mock:small", frontier="mock:frontier", judge="mock:judge")
    mock_text = render_markdown(await build(mock_meta))
    assert mock_text.index("mock provider") < mock_text.index("## 실행 정보")
    assert "mock provider" not in render_markdown(await build(make_meta()))


@pytest.mark.anyio
async def test_a_mock_judge_alone_invalidates_only_the_judge_dependent_numbers():
    # The likely first real run: real models, but no Jev access yet.
    text = render_markdown(await build(make_meta(judge="mock:judge")))
    assert "판정기가 mock입니다" in text
    assert "`all_small`·`all_frontier`·`rules` 행은 실제 측정값" in text
    assert "모델 응답이" not in text  # the blanket "everything is fake" warning is not shown


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("meta_kwargs", "parts"),
    [
        ({"small": "mock:small"}, ["소형 모델"]),
        ({"frontier": "mock:frontier", "judge": "mock:judge"}, ["상용 모델", "판정기"]),
        (
            {"small": "mock:small", "frontier": "mock:frontier", "judge": "mock:judge"},
            ["소형 모델", "상용 모델", "판정기"],
        ),
    ],
)
async def test_a_mock_model_makes_the_whole_report_meaningless_and_names_the_parts(
    meta_kwargs, parts
):
    data = await build(make_meta(**meta_kwargs))
    assert data.mock_parts == parts and data.uses_mock
    text = render_markdown(data)
    assert f"mock provider({', '.join(parts)})로 수집한 결과" in text
    assert "판정기가 mock입니다" not in text


@pytest.mark.anyio
async def test_summary_json_lists_which_parts_were_mock(tmp_path):
    data = await build(make_meta(judge="mock:judge"))
    summary = json.loads(write_report(data, tmp_path)[3].read_text(encoding="utf-8"))
    assert summary["mock_parts"] == ["판정기"] and summary["uses_mock"] is True


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("kwargs", "needle", "present"),
    [
        ({"labels_reviewed": False}, "검토 전 AI 초안", True),
        ({"labels_reviewed": True}, "검토 전 AI 초안", False),
        ({"labels_reviewed": None}, "검토 전 AI 초안", False),
        ({"dataset_changed": True}, "데이터셋 파일이 바뀌었습니다", True),
        ({"dataset_changed": False}, "데이터셋 파일이 바뀌었습니다", False),
    ],
)
async def test_warnings_appear_only_when_they_apply(kwargs, needle, present):
    assert (needle in render_markdown(await build(**kwargs))) is present


@pytest.mark.anyio
async def test_small_samples_always_carry_a_warning_about_the_intervals():
    assert "표본이 작습니다 (n=6)" in render_markdown(await build())


@pytest.mark.anyio
async def test_stale_missing_and_failed_items_are_excluded_with_reasons():
    meta = make_meta()
    cached = keyed(meta)
    cached["B"] = cached["B"].model_copy(update={"key": "from-another-model"})
    del cached["A"]
    data = await build(meta, cached)
    reasons = dict(data.excluded)
    assert reasons["B"].startswith("stale record")
    assert reasons["A"] == "not collected"
    assert data.n_usable == 4 and data.n_items == 6
    assert len(data.excluded) == 2  # each item is listed once


@pytest.mark.anyio
async def test_without_metadata_nothing_is_dropped_as_stale():
    data = await build_report_data("r", ITEMS, CACHED, RuleScorer(), TAUS, meta=None)
    assert data.n_usable == 6 and data.uses_mock is False
    assert "수집 메타데이터가 없습니다" in render_markdown(data)


@pytest.mark.anyio
async def test_write_report_creates_readable_files(tmp_path):
    data = await build()
    paths = write_report(data, tmp_path)
    assert [p.name for p in paths] == [
        "report.md",
        "configs.csv",
        "judge_quality.csv",
        "summary.json",
    ]
    assert all(p.parent == tmp_path / "r" and p.exists() for p in paths)

    with open(paths[1], encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert [r["name"] for r in rows] == [s.name for s in default_configs(TAUS)]
    hybrid = next(r for r in rows if r["name"] == "hybrid@0.7")
    assert float(hybrid["accuracy"]) == pytest.approx(5 / 6)

    with open(paths[2], encoding="utf-8", newline="") as f:
        assert len(list(csv.DictReader(f))) == len(TAUS) * 2  # two label sources per tau

    summary = json.loads(paths[3].read_text(encoding="utf-8"))
    assert summary["n_usable"] == 6 and summary["uses_mock"] is False
    assert len(summary["configs"]) == len(default_configs(TAUS))
    assert "라우팅 평가 리포트" in paths[0].read_text(encoding="utf-8")
