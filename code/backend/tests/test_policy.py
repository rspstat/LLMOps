import dataclasses
import hashlib

import pytest
from pydantic import ValidationError

from evals.cache import CachedItem, CallRecord, EvalCache, JudgeCall
from evals.collect import JudgeTarget, ModelTarget, make_key, pending_items
from evals.schema import EvalItem
from gateway.pipeline import Price
from gateway.settings import Settings
from gateway.wiring import build_router
from providers.decision import REQUEST_MARKER, ChoiceDecision, ChoiceQuestion
from router.hybrid_router import HybridConfig, HybridRouter
from router.policy import DEFAULT_POLICY_VERSION, POLICIES, V1, Policy, build_state, get_policy
from router.rule_router import RuleRouter

# sha256 of build_state("", V1) when v1 was published (2026-10-13). Real measurements, trace
# events and the evaluation cache are labelled "v1", so its wording must never change: a new
# wording is a new version.
V1_STATE_SHA256 = "2617ba8a32df01f502e703460d9ca5735fafbb6411c52994f1200245c5b60f53"


def test_v1_wording_is_frozen():
    assert hashlib.sha256(build_state("", V1).encode("utf-8")).hexdigest() == V1_STATE_SHA256
    assert V1.question.key == "difficulty"
    assert V1.question.instructions == "How difficult is it to answer the request well?"
    assert V1.question.criteria == {
        "easy": "A small model would answer this as well as a large one.",
        "hard": "A large model is needed for a good answer, or it is unclear.",
    }


def test_registry_is_consistent():
    assert DEFAULT_POLICY_VERSION in POLICIES
    for version, policy in POLICIES.items():
        assert policy.version == version
        assert policy.text.strip()
        # The router only knows these two answers.
        assert set(policy.question.criteria) == {"easy", "hard"}
        assert get_policy(version) is policy


def test_unknown_policy_names_the_known_ones():
    with pytest.raises(ValueError, match=r"'v9'.*v1"):
        get_policy("v9")


def test_build_state_puts_the_request_after_the_marker():
    state = build_state("what is 2+2", V1)

    assert state == f"{V1.text}\n\n{REQUEST_MARKER}\nwhat is 2+2"
    assert build_state("what is 2+2") == build_state(
        "what is 2+2", get_policy(DEFAULT_POLICY_VERSION)
    )


def test_settings_default_and_validation():
    assert Settings(_env_file=None).router_policy == DEFAULT_POLICY_VERSION
    with pytest.raises(ValidationError, match="unknown routing policy"):
        Settings(_env_file=None, router_policy="v9")


class RecordingJudge:
    name = "recording-judge"

    def __init__(self) -> None:
        self.calls: list[tuple[str, ChoiceQuestion]] = []

    async def decide(self, state: str, question: ChoiceQuestion) -> ChoiceDecision:
        self.calls.append((state, question))
        return ChoiceDecision("easy", {"easy": 0.9, "hard": 0.1}, 0.9, "j", 1, 1)


@pytest.mark.anyio
@pytest.mark.parametrize("version", sorted(POLICIES))
async def test_router_sends_the_configured_policy_and_records_its_version(version):
    policy = get_policy(version)
    judge = RecordingJudge()
    router = HybridRouter(RuleRouter(), judge, HybridConfig(0.7, policy=policy))

    decision = await router.route("what is 2+2")

    [(state, question)] = judge.calls
    assert state == build_state("what is 2+2", policy)
    assert question is policy.question
    assert decision.judge.policy_version == version
    assert decision.detail["policy_version"] == version


@pytest.mark.parametrize("version", sorted(POLICIES))
def test_wiring_builds_the_router_with_the_policy_from_settings(version):
    router = build_router(Settings(_env_file=None, router_mode="hybrid", router_policy=version))

    assert router.config.policy is get_policy(version)


def other_policy() -> Policy:
    return dataclasses.replace(V1, version="vX", text=V1.text + "\nExtra sentence.")


def eval_item() -> EvalItem:
    return EvalItem(
        id="i1",
        prompt="question one",
        lang="en",
        category="math",
        difficulty="easy",
        answer_type="exact",
        reference=["x"],
    )


def eval_targets(policy: Policy | None = None):
    small = ModelTarget(object(), "s1", Price())
    frontier = ModelTarget(object(), "f1", Price())
    judge = (
        JudgeTarget(object(), "j1", Price(), policy)
        if policy
        else JudgeTarget(object(), "j1", Price())
    )
    return small, frontier, judge


def test_evaluation_cache_key_includes_the_policy_version():
    item = eval_item()
    small, frontier, judge_v1 = eval_targets()
    _, _, judge_x = eval_targets(other_policy())

    assert make_key(item, small, frontier, judge_v1, 64) != make_key(
        item, small, frontier, judge_x, 64
    )


def test_records_collected_under_another_policy_are_pending_again(tmp_path):
    item = eval_item()
    small, frontier, judge_v1 = eval_targets()
    _, _, judge_x = eval_targets(other_policy())
    cache = EvalCache(tmp_path, "run")
    cache.append(
        CachedItem(
            item_id=item.id,
            key=make_key(item, small, frontier, judge_v1, 64),
            judge=JudgeCall(),
            small=CallRecord(),
            frontier=CallRecord(),
        )
    )

    assert pending_items([item], cache, small, frontier, judge_v1, 64) == []
    assert pending_items([item], cache, small, frontier, judge_x, 64) == [item]
