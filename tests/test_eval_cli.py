import json

import httpx
import pytest

from evals import run
from evals.cache import EvalCache
from evals.schema import load_items
from gateway.settings import Settings

MOCK = Settings(_env_file=None)
LIVE_SLM = Settings(_env_file=None, small_provider="slm", slm_model="tiny")


@pytest.fixture(autouse=True)
def no_real_network(monkeypatch):
    """Nothing in this module may reach the network, even by accident."""

    def boom(*args, **kwargs):
        raise AssertionError("eval CLI test attempted real network access")

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", boom)


def cli(argv, tmp_path, *, environ=None, settings=MOCK):
    base = ["--cache-dir", str(tmp_path / "cache")]
    command = argv[0]
    extra = base if command in ("collect", "report") else []
    if command == "report":
        extra = extra + ["--out-dir", str(tmp_path / "reports")]
    return run.main([command, *extra, *argv[1:]], environ or {}, settings=settings)


def test_validate_reports_the_dataset_and_the_unreviewed_labels(tmp_path, capsys):
    assert cli(["validate"], tmp_path) == 0
    out = capsys.readouterr().out
    assert "80 items valid (40 en, 40 ko)" in out and "unreviewed" in out


def test_validate_rejects_a_broken_dataset(tmp_path, capsys):
    bad = tmp_path / "bad.jsonl"
    bad.write_text('{"id": "x", "prompt": "p"}\n', encoding="utf-8")
    assert cli(["validate", "--dataset", str(bad)], tmp_path) == 1
    assert "bad.jsonl:1" in capsys.readouterr().err


def test_select_items_is_deterministic_and_spreads_over_languages():
    items = load_items(run.DEFAULT_DATASET)
    first, second = run.select_items(items, 10), run.select_items(items, 10)
    assert [i.id for i in first] == [i.id for i in second]
    assert {i.lang for i in first} == {"en", "ko"} and len({i.category for i in first}) >= 3
    assert len(run.select_items(items, None)) == 80


def test_mock_collect_writes_cache_and_metadata_then_reuses_it(tmp_path, capsys):
    assert cli(["collect", "--name", "m", "--limit", "10"], tmp_path) == 0
    assert "collected 10, reused 0, calls 30" in capsys.readouterr().out
    cache = EvalCache(tmp_path / "cache", "m")
    assert len(cache.load()) == 10
    meta = cache.read_meta()
    assert (meta.small, meta.frontier, meta.judge) == ("mock:small", "mock:frontier", "mock:judge")
    assert meta.policy_version == "v1" and meta.max_tokens == 64

    assert cli(["collect", "--name", "m", "--limit", "10"], tmp_path) == 0
    assert "collected 0, reused 10, calls 0" in capsys.readouterr().out


def test_max_tokens_is_capped(tmp_path):
    assert cli(["collect", "--name", "m", "--limit", "2", "--max-tokens", "99999"], tmp_path) == 0
    assert EvalCache(tmp_path / "cache", "m").read_meta().max_tokens == run.MAX_TOKENS_CAP


def test_dry_run_estimates_and_writes_nothing(tmp_path, capsys):
    assert cli(["collect", "--name", "m", "--dry-run"], tmp_path) == 0
    out = capsys.readouterr().out
    assert "240 calls" in out and "dry run: nothing was called" in out and "[mock]" in out
    assert not (tmp_path / "cache").exists()


def test_zero_budget_stops_before_the_first_item(tmp_path, capsys):
    assert cli(["collect", "--name", "m", "--budget-usd", "0"], tmp_path) == 0
    out = capsys.readouterr().out
    assert "collected 0" in out and "budget $0.0 reached" in out


def test_live_collect_is_refused_without_the_shell_flag(tmp_path, capsys):
    assert cli(["collect", "--name", "m", "--budget-usd", "1"], tmp_path, settings=LIVE_SLM) == 2
    assert "ALLOW_LIVE_CALLS=1" in capsys.readouterr().err
    assert not (tmp_path / "cache").exists()


def test_live_collect_is_refused_without_a_budget_even_with_the_flag(tmp_path, capsys):
    code = cli(
        ["collect", "--name", "m"], tmp_path, environ={"ALLOW_LIVE_CALLS": "1"}, settings=LIVE_SLM
    )
    assert code == 2 and "--budget-usd" in capsys.readouterr().err
    assert not (tmp_path / "cache").exists()


@pytest.mark.parametrize("flag", ["0", "true", ""])
def test_only_the_exact_value_one_enables_live_calls(tmp_path, flag):
    code = cli(
        ["collect", "--name", "m", "--budget-usd", "1"],
        tmp_path,
        environ={"ALLOW_LIVE_CALLS": flag},
        settings=LIVE_SLM,
    )
    assert code == 2


def test_live_dry_run_needs_no_flag_and_calls_nothing(tmp_path, capsys):
    assert (
        cli(["collect", "--name", "m", "--dry-run", "--limit", "5"], tmp_path, settings=LIVE_SLM)
        == 0
    )
    out = capsys.readouterr().out
    assert "[LIVE]" in out and "nothing was called" in out


def test_report_needs_collected_data(tmp_path, capsys):
    assert cli(["report", "--name", "nothing"], tmp_path) == 1
    assert "Run `collect` first" in capsys.readouterr().err


def test_report_after_a_mock_collect_writes_files_and_flags_mock(tmp_path, capsys):
    cli(["collect", "--name", "m", "--limit", "20"], tmp_path)
    capsys.readouterr()
    assert cli(["report", "--name", "m", "--taus", "0.6,0.8"], tmp_path) == 0
    printed = capsys.readouterr().out.split()
    assert any(p.endswith("report.md") for p in printed)

    report_dir = tmp_path / "reports" / "m"
    text = (report_dir / "report.md").read_text(encoding="utf-8")
    assert "mock provider" in text and "`hybrid@0.6`" in text and "`judge_only@0.8`" in text
    assert "검토 전 AI 초안" in text  # the shipped dataset's labels are not reviewed yet
    summary = json.loads((report_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["n_usable"] == 20 and summary["uses_mock"] is True


def test_recollecting_with_other_settings_never_mixes_runs_in_the_report(tmp_path, capsys):
    cli(["collect", "--name", "m", "--limit", "10", "--max-tokens", "64"], tmp_path)
    cli(["collect", "--name", "m", "--limit", "5", "--max-tokens", "32"], tmp_path)  # new settings
    capsys.readouterr()
    assert cli(["report", "--name", "m"], tmp_path) == 0
    summary = json.loads((tmp_path / "reports" / "m" / "summary.json").read_text(encoding="utf-8"))
    stale = [i for i, why in summary["excluded"] if why.startswith("stale record")]
    assert summary["n_usable"] == 5 and len(stale) == 5  # 10 records on disk, only 5 match the meta
