import pytest
from pydantic import ValidationError

from evals.schema import EvalItem
from evals.scorers import RuleScorer, Scorer, extract_number, normalize


def item(answer_type: str, reference: list[str], **overrides) -> EvalItem:
    fields = {
        "id": "t1",
        "prompt": "p",
        "lang": "en",
        "category": "factual",
        "difficulty": "easy",
        "answer_type": answer_type,
        "reference": reference,
    }
    return EvalItem(**(fields | overrides))


SCORER = RuleScorer()


def test_rule_scorer_satisfies_scorer_protocol():
    assert isinstance(SCORER, Scorer)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  Paris. ", "paris"),
        ("**Paris**", "paris"),
        ("“서울”。", "서울"),
        ("ＨＥＬＬＯ　ｗｏｒｌｄ", "hello world"),  # full-width forms fold under NFKC
        ("a   b\n c", "a b c"),
        ("7:30", "7:30"),  # inner punctuation is kept
    ],
)
def test_normalize(raw, expected):
    assert normalize(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("42", 42.0),
        (" 15,000원", 15000.0),
        ("$21.00", 21.0),
        ("-3", -3.0),
        ("The answer is 75.", 75.0),
        ("first 10 then 20", 20.0),  # documented: last number wins
        ("７５", 75.0),
        ("no digits here", None),
        ("", None),
    ],
)
def test_extract_number(raw, expected):
    assert extract_number(raw) == expected


def test_exact_ignores_case_and_edge_punctuation_but_not_extra_words():
    it = item("exact", ["receive"])
    assert SCORER.score(it, "Receive.") is True
    assert SCORER.score(it, "The word is receive") is False
    assert SCORER.score(it, "receipt") is False


def test_contains_accepts_any_reference_inside_a_longer_answer():
    it = item("contains", ["paris"])
    assert SCORER.score(it, "The capital of France is Paris.") is True
    assert SCORER.score(it, "Lyon") is False
    multi = item("contains", ["halb acht", "7:30"], lang="en")
    assert SCORER.score(multi, "Der Zug fährt um 7:30 Uhr ab.") is True


def test_choice_accepts_the_word_or_its_first_word_only():
    it = item("choice", ["yes"])
    assert SCORER.score(it, "Yes") is True
    assert SCORER.score(it, "Yes, they contradict each other.") is True
    assert SCORER.score(it, "I think yes") is False  # first word is not the label
    assert SCORER.score(it, "no") is False


def test_choice_works_for_korean_labels():
    it = item("choice", ["예", "네"], lang="ko")
    assert SCORER.score(it, "예.") is True
    assert SCORER.score(it, "네, 모순됩니다.") is True
    assert SCORER.score(it, "아니오") is False


def test_number_compares_numerically_with_tolerance_and_alternatives():
    it = item("number", ["21"])
    assert SCORER.score(it, "21.00") is True
    assert SCORER.score(it, "$21") is True
    assert SCORER.score(it, "22") is False
    assert SCORER.score(it, "I don't know") is False
    assert SCORER.score(item("number", ["0.1"]), "0.1000000001") is True
    assert SCORER.score(item("number", ["3", "4"]), "4") is True


def test_open_items_cannot_be_scored():
    assert SCORER.score(item("open", []), "anything at all") is None


@pytest.mark.parametrize(
    "bad",
    [
        {"answer_type": "exact", "reference": []},
        {"answer_type": "contains", "reference": ["  "]},
        {"answer_type": "number", "reference": ["abc"]},
        {"answer_type": "open", "reference": ["x"]},
        {"lang": "fr"},
        {"difficulty": "medium"},
        {"category": "poetry"},
        {"prompt": ""},
        {"unknown_field": 1},
    ],
)
def test_item_validation_rejects_inconsistent_items(bad):
    valid = {
        "id": "t",
        "prompt": "p",
        "lang": "en",
        "category": "math",
        "difficulty": "easy",
        "answer_type": "exact",
        "reference": ["ok"],
    }
    assert EvalItem(**valid)  # the baseline is valid, so each failure is caused by `bad`
    with pytest.raises(ValidationError):
        EvalItem(**(valid | bad))
