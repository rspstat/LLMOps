from router.base import Route
from router.rule_router import RouterConfig, RuleRouter


def test_short_plain_question_goes_to_small_with_low_confidence():
    decision = RuleRouter().decide("What is the capital of France?")
    assert decision.route is Route.SMALL
    assert decision.reason == "default_small"
    assert decision.confidence == 0.5


def test_long_prompt_threshold_is_inclusive_and_configurable():
    router = RuleRouter(RouterConfig(long_prompt_chars=20, frontier_keywords=()))
    assert router.decide("a" * 19).route is Route.SMALL
    decision = router.decide("a" * 20)
    assert decision.route is Route.FRONTIER
    assert decision.reason == "long_prompt"
    assert decision.confidence == 1.0


def test_keyword_match_is_case_insensitive_and_reports_the_keyword():
    decision = RuleRouter().decide("Please ANALYZE this log")
    assert decision.route is Route.FRONTIER
    assert decision.reason == "keyword:analyze"
    assert decision.confidence == 1.0


def test_korean_keyword_routes_to_frontier():
    decision = RuleRouter().decide("이 구조를 단계별로 설명해줘")
    assert decision.route is Route.FRONTIER
    assert decision.reason == "keyword:단계별"


def test_custom_keywords_replace_defaults():
    router = RuleRouter(RouterConfig(frontier_keywords=("sql",)))
    assert router.decide("write some SQL").route is Route.FRONTIER
    assert router.decide("please analyze this").route is Route.SMALL


def test_default_confidence_is_configurable():
    router = RuleRouter(RouterConfig(default_confidence=0.2))
    assert router.decide("hi").confidence == 0.2
