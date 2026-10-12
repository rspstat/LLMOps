"""Routing evaluation CLI.

    uv run python -m evals.run validate
    uv run python -m evals.run collect --name mock-run --limit 20        # offline mocks by default
    uv run python -m evals.run report  --name mock-run
    # real models: set SMALL_PROVIDER / FRONTIER_PROVIDER / JUDGE_PROVIDER in .env, then
    ALLOW_LIVE_CALLS=1 uv run python -m evals.run collect --name real --budget-usd 0.25

`collect` is the only step that can call models. With anything other than the mock providers it
refuses to run unless ALLOW_LIVE_CALLS=1 is set in the shell AND --budget-usd is given
(--dry-run prints the estimate and calls nothing). `report` only reads the cache.
"""

import argparse
import asyncio
import hashlib
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

from dotenv import dotenv_values

from evals.cache import CacheMeta, EvalCache
from evals.check import diagnose
from evals.collect import JudgeTarget, ModelTarget, collect, estimate, pending_items
from evals.report import build_report_data, write_report
from evals.schema import EvalItem, file_hash, load_items
from evals.scorers import RuleScorer
from gateway.pipeline import Price
from gateway.settings import Settings
from gateway.wiring import build_judge, build_registry
from router.policy import POLICY_VERSION

DEFAULT_DATASET = "evals/datasets/routing_v1.jsonl"
DEFAULT_CACHE_DIR = "evals/cache"
DEFAULT_OUT_DIR = "evals/reports"
DEFAULT_TAUS = "0.5,0.6,0.7,0.8,0.9"
DEFAULT_MAX_TOKENS = 64
MAX_TOKENS_CAP = 256

EXIT_OK, EXIT_ERROR, EXIT_REFUSED = 0, 1, 2


def is_live(settings: Settings) -> bool:
    return (
        settings.small_provider != "mock"
        or settings.frontier_provider != "mock"
        or settings.judge_provider != "mock"
    )


def build_targets(settings: Settings) -> tuple[ModelTarget, ModelTarget, JudgeTarget]:
    registry = build_registry(settings)
    small_id = (
        "mock:small"
        if settings.small_provider == "mock"
        else f"slm:{settings.slm_model}@{settings.slm_base_url}"
    )
    frontier_id = (
        "mock:frontier"
        if settings.frontier_provider == "mock"
        else f"openai:{settings.frontier_model}@{settings.frontier_base_url}"
    )
    judge_id = (
        "mock:judge"
        if settings.judge_provider == "mock"
        else f"jev:{settings.jev_model}@{settings.jev_base_url}"
    )
    return (
        ModelTarget(
            registry.routes["small"],
            small_id,
            Price(settings.small_price_in_per_mtok, settings.small_price_out_per_mtok),
        ),
        ModelTarget(
            registry.routes["frontier"],
            frontier_id,
            Price(settings.frontier_price_in_per_mtok, settings.frontier_price_out_per_mtok),
        ),
        JudgeTarget(
            build_judge(settings),
            judge_id,
            Price(settings.jev_price_in_per_mtok, settings.jev_price_out_per_mtok),
        ),
    )


def unpriced_paid_parts(
    settings: Settings, small: ModelTarget, frontier: ModelTarget, judge: JudgeTarget
) -> list[str]:
    """Live components that bill per token but have no price configured.

    The budget guard sums price x tokens, so a zero price silently disables it for that
    component. A self-hosted small model (no API key) is legitimately free; one behind an API
    key is a hosted, billed service.
    """
    missing = []
    hosted_small = settings.small_provider != "mock" and bool(
        settings.slm_api_key.get_secret_value()
    )
    if hosted_small and small.price == Price():
        missing.append("SMALL_PRICE_IN_PER_MTOK / SMALL_PRICE_OUT_PER_MTOK")
    if settings.frontier_provider != "mock" and frontier.price == Price():
        missing.append("FRONTIER_PRICE_IN_PER_MTOK / FRONTIER_PRICE_OUT_PER_MTOK")
    if settings.judge_provider != "mock" and judge.price == Price():
        missing.append("JEV_PRICE_IN_PER_MTOK / JEV_PRICE_OUT_PER_MTOK")
    return missing


def select_items(items: Sequence[EvalItem], limit: int | None) -> list[EvalItem]:
    """A deterministic spread over languages and categories (file order is grouped, so the first
    N items would be all English / all factual)."""
    if limit is None:
        return list(items)
    return sorted(items, key=lambda i: hashlib.sha256(i.id.encode()).hexdigest())[:limit]


def _cmd_check(args: argparse.Namespace, settings: Settings | None) -> int:
    """Explain what .env will do. Prints names, on/off states and hosts, never key values."""
    env_path = Path(args.env_file)
    defined = dotenv_values(env_path) if env_path.exists() else {}
    settings = settings or Settings(_env_file=env_path)
    lines, problems = diagnose(settings, defined, env_path.exists())
    print(f"{env_path}: {len(defined)}개 변수 정의됨" if env_path.exists() else f"{env_path}: 없음")
    for line in lines:
        print(line)
    if not problems:
        print("\n문제 없음: 설정이 서로 모순되지 않습니다.")
        return EXIT_OK
    print(f"\n고쳐야 할 것 {len(problems)}개:")
    for number, problem in enumerate(problems, start=1):
        print(f"  {number}. {problem}")
    return EXIT_ERROR


def _cmd_validate(args: argparse.Namespace) -> int:
    items = load_items(args.dataset)
    by_lang = {lang: sum(1 for i in items if i.lang == lang) for lang in ("en", "ko")}
    print(f"{args.dataset}: {len(items)} items valid ({by_lang['en']} en, {by_lang['ko']} ko)")
    meta = Path(args.dataset).with_suffix(".meta.json")
    if meta.exists() and '"labels_reviewed": false' in meta.read_text(encoding="utf-8"):
        print("note: difficulty labels are still an unreviewed AI draft (labels_reviewed=false)")
    return EXIT_OK


def _cmd_collect(
    args: argparse.Namespace,
    environ: Mapping[str, str],
    settings: Settings,
    log: Callable[[str], None],
) -> int:
    items = select_items(load_items(args.dataset), args.limit)
    max_tokens = max(1, min(args.max_tokens, MAX_TOKENS_CAP))
    small, frontier, judge = build_targets(settings)
    cache = EvalCache(args.cache_dir, args.name)
    todo = pending_items(items, cache, small, frontier, judge, max_tokens)
    est = estimate(todo, small, frontier, judge, max_tokens)

    live = is_live(settings)
    mode = "LIVE" if live else "mock"
    print(
        f"{len(items)} items selected, {len(todo)} to collect "
        f"({est.calls} calls, ~{est.input_tokens} input tokens, "
        f"up to {est.max_output_tokens} output tokens, est. cost <= ${est.cost_usd:.4f}) [{mode}]"
    )
    unpriced = unpriced_paid_parts(settings, small, frontier, judge)
    if unpriced:
        print(
            f"WARNING: no price set for {', '.join(unpriced)}. The estimate above and --budget-usd "
            "would treat those calls as free.",
            file=sys.stderr,
        )
    if args.dry_run:
        print("dry run: nothing was called")
        return EXIT_OK

    if live:
        if environ.get("ALLOW_LIVE_CALLS") != "1":
            print(
                "Refusing live calls: set ALLOW_LIVE_CALLS=1 in the shell for this run.",
                file=sys.stderr,
            )
            return EXIT_REFUSED
        if args.budget_usd is None:
            print(
                "Refusing live calls without --budget-usd (use --dry-run to see the estimate).",
                file=sys.stderr,
            )
            return EXIT_REFUSED
        if unpriced:
            print(
                "Refusing live calls: the budget cannot be enforced without prices. Set "
                f"{', '.join(unpriced)} in .env (USD per 1M tokens, from the price list).",
                file=sys.stderr,
            )
            return EXIT_REFUSED

    cache.write_meta(
        CacheMeta(
            name=args.name,
            created_at=datetime.now(UTC).isoformat(),
            dataset=file_hash(args.dataset),
            small=small.identity,
            frontier=frontier.identity,
            judge=judge.identity,
            policy_version=POLICY_VERSION,
            max_tokens=max_tokens,
            prices={
                "small": {
                    "input": small.price.input_per_mtok,
                    "output": small.price.output_per_mtok,
                },
                "frontier": {
                    "input": frontier.price.input_per_mtok,
                    "output": frontier.price.output_per_mtok,
                },
                "judge": {
                    "input": judge.price.input_per_mtok,
                    "output": judge.price.output_per_mtok,
                },
            },
        )
    )
    stats = asyncio.run(
        collect(
            items,
            cache,
            small=small,
            frontier=frontier,
            judge=judge,
            max_tokens=max_tokens,
            budget_usd=args.budget_usd,
            progress=log,
        )
    )
    print(
        f"collected {stats.collected}, reused {stats.reused}, calls {stats.calls}, "
        f"spent ${stats.spent_usd:.6f}"
    )
    if stats.failed_items:
        print(
            f"{len(stats.failed_items)} item(s) had a failed call "
            "(recorded, and excluded from the report)"
        )
    if stats.empty_answers:
        print(
            f"WARNING: {len(stats.empty_answers)} item(s) got an EMPTY answer from a model. "
            "This is typical of a reasoning model that spent its whole --max-tokens budget "
            "thinking; those answers are scored wrong. Use a non-reasoning chat model or raise "
            f"--max-tokens (cap {MAX_TOKENS_CAP}). First: {', '.join(stats.empty_answers[:3])}",
            file=sys.stderr,
        )
    if stats.stopped_by_budget:
        print(f"stopped: budget ${args.budget_usd} reached; run again to continue from the cache")
    return EXIT_OK


def _cmd_report(args: argparse.Namespace) -> int:
    items = load_items(args.dataset)
    cache = EvalCache(args.cache_dir, args.name)
    cached = cache.load()
    if not cached:
        print(
            f"No collected data for '{args.name}' in {args.cache_dir}. Run `collect` first.",
            file=sys.stderr,
        )
        return EXIT_ERROR
    meta = cache.read_meta()
    meta_file = Path(args.dataset).with_suffix(".meta.json")
    labels_reviewed = None
    if meta_file.exists():
        labels_reviewed = '"labels_reviewed": true' in meta_file.read_text(encoding="utf-8")
    taus = [float(t) for t in args.taus.split(",") if t.strip()]
    data = asyncio.run(
        build_report_data(
            args.name,
            items,
            cached,
            RuleScorer(),
            taus,
            meta=meta,
            dataset_changed=bool(meta and meta.dataset != file_hash(args.dataset)),
            labels_reviewed=labels_reviewed,
        )
    )
    if data.n_usable == 0:
        print(
            "No usable items (every item is missing, stale or had a failed model call).",
            file=sys.stderr,
        )
        return EXIT_ERROR
    for path in write_report(data, args.out_dir):
        print(path)
    return EXIT_OK


def main(
    argv: Sequence[str] | None = None,
    environ: Mapping[str, str] | None = None,
    *,
    settings: Settings | None = None,
) -> int:
    environ = os.environ if environ is None else environ
    parser = argparse.ArgumentParser(prog="evals.run", description="Routing evaluation.")
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--dataset", default=DEFAULT_DATASET)

    def named(p: argparse.ArgumentParser) -> None:
        common(p)
        p.add_argument("--name", default="run", help="cache / report name")
        p.add_argument("--cache-dir", default=DEFAULT_CACHE_DIR)

    common(sub.add_parser("validate", help="check the dataset file"))

    check_p = sub.add_parser("check", help="explain what .env will do (never prints key values)")
    check_p.add_argument("--env-file", default=".env")

    collect_p = sub.add_parser("collect", help="call the judge and both models once per item")
    named(collect_p)
    collect_p.add_argument("--limit", type=int, help="use a deterministic sample of N items")
    collect_p.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    collect_p.add_argument(
        "--budget-usd", type=float, help="stop starting new items once this is spent"
    )
    collect_p.add_argument(
        "--dry-run", action="store_true", help="print the estimate, call nothing"
    )

    report_p = sub.add_parser(
        "report", help="replay configurations over the cache and write a report"
    )
    named(report_p)
    report_p.add_argument("--taus", default=DEFAULT_TAUS, help="comma-separated promote thresholds")
    report_p.add_argument("--out-dir", default=DEFAULT_OUT_DIR)

    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
            return _cmd_validate(args)
        if args.command == "check":
            return _cmd_check(args, settings)
        if args.command == "collect":
            return _cmd_collect(args, environ, settings or Settings(), print)
        return _cmd_report(args)
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
