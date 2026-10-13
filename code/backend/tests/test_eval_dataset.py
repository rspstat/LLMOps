import json
import re
from collections import Counter
from pathlib import Path

import pytest

from evals.schema import load_items
from evals.scorers import RuleScorer, normalize
from guards.input_guard import InputGuard
from router.rule_router import RuleRouter

DATASET = Path("evals/datasets/routing_v1.jsonl")
META = Path("evals/datasets/routing_v1.meta.json")

ITEMS = load_items(DATASET)
SCORER = RuleScorer()


def test_dataset_has_the_documented_shape():
    assert len(ITEMS) == 80
    assert Counter(i.lang for i in ITEMS) == {"en": 40, "ko": 40}
    cells = Counter((i.lang, i.category) for i in ITEMS)
    assert len(cells) == 10 and set(cells.values()) == {8}


def test_ids_and_prompts_are_unique():
    assert len({i.id for i in ITEMS}) == len(ITEMS)
    assert len({normalize(i.prompt) for i in ITEMS}) == len(ITEMS)


def test_every_language_and_category_has_both_difficulties():
    seen = Counter((i.lang, i.category, i.difficulty) for i in ITEMS)
    assert all(
        seen[(lang, cat, diff)] >= 3
        for lang in ("en", "ko")
        for cat in ("factual", "transform", "math", "classify", "reasoning")
        for diff in ("easy", "hard")
    )


def test_all_items_are_machine_scorable():
    assert all(i.answer_type != "open" for i in ITEMS)


@pytest.mark.parametrize("item", ITEMS, ids=lambda i: i.id)
def test_reference_answer_scores_correct_and_junk_does_not(item):
    # Guards against typos in references and against normalisation mismatches.
    for ref in item.reference:
        assert SCORER.score(item, ref) is True, f"{item.id}: reference {ref!r} does not score"
    for junk in ("", "zzz", "I do not know", "모르겠습니다"):
        assert SCORER.score(item, junk) is False, f"{item.id}: {junk!r} scored as correct"


@pytest.mark.parametrize("item", ITEMS, ids=lambda i: i.id)
def test_repeating_the_prompt_is_never_a_correct_answer(item):
    # Found with the mock provider, which echoes the prompt: 14 items used to "pass" because the
    # reference appeared in the prompt itself, or the answer equalled an operand.
    assert SCORER.score(item, item.prompt) is False
    assert SCORER.score(item, "[mock-small] " + item.prompt[:80]) is False


CHOICE_ITEMS = [i for i in ITEMS if i.answer_type == "choice"]


@pytest.mark.parametrize("item", CHOICE_ITEMS, ids=lambda i: i.id)
def test_listing_the_options_is_never_a_correct_answer(item):
    for first in item.options:
        for second in item.options:
            if first == second:
                continue
            for joined in (f"{first} or {second}", f"{first}, {second}", f"{first}/{second}"):
                assert SCORER.score(item, joined) is False, f"{item.id}: {joined!r}"
    assert SCORER.score(item, " ".join(item.options)) is False


@pytest.mark.parametrize("item", CHOICE_ITEMS, ids=lambda i: i.id)
def test_choice_items_declare_the_options_their_prompt_offers(item):
    options = [normalize(o) for o in item.options]
    assert len(options) >= 2
    assert any(normalize(r) in options for r in item.reference)  # the right answer is an option
    prompt = normalize(item.prompt)
    assert all(o in prompt for o in options), f"{item.id}: an option is not in the prompt"


def test_no_prompt_is_blocked_by_the_default_input_guard_or_length_rule():
    guard = InputGuard()
    router = RuleRouter()
    for item in ITEMS:
        assert not guard.check(item.prompt).blocked, item.id
        assert len(item.prompt) < router.config.long_prompt_chars, item.id


def test_default_keyword_rules_fire_on_both_easy_and_hard_prompts():
    # Otherwise "rules" mode would trivially equal "all small" and the comparison means nothing.
    router = RuleRouter()
    fired = [i for i in ITEMS if router.decide(i.prompt).route.value == "frontier"]
    assert sum(i.difficulty == "easy" for i in fired) >= 4
    assert sum(i.difficulty == "hard" for i in fired) >= 4


def test_no_personal_data_patterns():
    patterns = [
        r"[\w.+-]+@[\w-]+\.[\w.]+",  # email
        r"https?://",  # links
        r"\b\d{2,3}-\d{3,4}-\d{4}\b",  # phone numbers
        r"\b\d{6}-\d{7}\b",  # Korean resident registration number
    ]
    for item in ITEMS:
        for pattern in patterns:
            assert not re.search(pattern, item.prompt), f"{item.id} matches {pattern}"


def test_meta_file_matches_the_dataset_and_flags_unreviewed_labels():
    meta = json.loads(META.read_text(encoding="utf-8"))
    assert meta["items"] == len(ITEMS)
    assert isinstance(meta["labels_reviewed"], bool)
