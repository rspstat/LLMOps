import json
from collections import Counter
from pathlib import Path

import pytest

from evals.schema import load_items
from evals.scorers import RuleScorer, normalize
from router.rule_router import RuleRouter

DATASETS = Path("evals/datasets")
HOLDOUT = DATASETS / "routing_v1_holdout.jsonl"
META = DATASETS / "routing_v1_holdout.meta.json"

ITEMS = load_items(HOLDOUT)
DEV_ITEMS = load_items(DATASETS / "routing_v1.jsonl")
SCORER = RuleScorer()


def test_holdout_has_the_documented_shape():
    assert len(ITEMS) == 60
    assert Counter(i.lang for i in ITEMS) == {"en": 30, "ko": 30}
    cells = Counter((i.lang, i.category, i.difficulty) for i in ITEMS)
    assert len(cells) == 20 and set(cells.values()) == {3}  # 2 langs x 5 categories x 2 levels


def test_holdout_shares_nothing_with_the_dev_set():
    assert not {i.id for i in ITEMS} & {i.id for i in DEV_ITEMS}
    assert not {normalize(i.prompt) for i in ITEMS} & {normalize(i.prompt) for i in DEV_ITEMS}
    assert len({normalize(i.prompt) for i in ITEMS}) == len(ITEMS)


def test_holdout_is_frozen_and_says_it_is_unreviewed():
    meta = json.loads(META.read_text(encoding="utf-8"))
    assert meta["frozen"] is True and meta["items"] == len(ITEMS)
    assert meta["labels_reviewed"] is False


def test_no_holdout_prompt_trips_the_rule_router_by_accident():
    # The holdout measures the judge. A keyword hit would route around it (and 'approved'
    # contains 'prove', as one dev item shows), so none are allowed here.
    rules = RuleRouter()
    assert [i.id for i in ITEMS if rules.decide(i.prompt).route.value == "frontier"] == []


@pytest.mark.parametrize("item", ITEMS, ids=lambda i: i.id)
def test_reference_scores_correct_and_junk_does_not(item):
    for ref in item.reference:
        assert SCORER.score(item, ref) is True, f"{item.id}: reference {ref!r} does not score"
    for junk in ("", "zzz", "I do not know", "모르겠습니다"):
        assert SCORER.score(item, junk) is False, f"{item.id}: {junk!r} scored as correct"


@pytest.mark.parametrize("item", ITEMS, ids=lambda i: i.id)
def test_repeating_the_prompt_is_never_a_correct_answer(item):
    # The mock provider echoes the prompt; an item that echo can pass would inflate every number.
    assert SCORER.score(item, item.prompt) is False
    assert SCORER.score(item, "[mock-small] " + item.prompt[:80]) is False
    if len(item.options) > 1:  # hedging by listing every option must not pass either
        assert SCORER.score(item, " or ".join(item.options)) is False
