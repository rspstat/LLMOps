from gateway.pipeline import Pipeline, Price
from gateway.settings import Settings
from guards.input_guard import InputGuard, InputGuardConfig
from providers.decision import DecisionProvider
from providers.jev import JevProvider
from providers.mock import MockProvider
from providers.mock_decision import MockDecisionProvider
from providers.openai_compat import OpenAICompatProvider
from providers.registry import ProviderRegistry
from router.base import Router
from router.hybrid_router import HybridConfig, HybridRouter
from router.policy import get_policy
from router.rule_router import RouterConfig, RuleRouter


def build_registry(settings: Settings) -> ProviderRegistry:
    if settings.small_provider == "slm":
        small = OpenAICompatProvider(
            "slm",
            base_url=settings.slm_base_url,
            model=settings.slm_model,
            api_key=settings.slm_api_key.get_secret_value() or None,
            timeout_s=settings.provider_timeout_s,
            extra_body=settings.slm_extra_body,
        )
    else:
        small = MockProvider("mock-small")

    if settings.frontier_provider == "openai":
        frontier = OpenAICompatProvider(
            "openai",
            base_url=settings.frontier_base_url,
            model=settings.frontier_model,
            api_key=settings.openai_api_key.get_secret_value(),
            timeout_s=settings.provider_timeout_s,
            extra_body=settings.frontier_extra_body,
        )
    else:
        frontier = MockProvider("mock-frontier")

    # No stand-in provider: if one route's model is down the other route's model answers, and
    # if both are down the request fails with 502. (All-mock dev mode never fails over to
    # anything but its own mocks.)
    return ProviderRegistry(routes={"small": small, "frontier": frontier})


def build_judge(settings: Settings) -> DecisionProvider:
    if settings.judge_provider == "jev":
        return JevProvider(
            "jev",
            url=settings.jev_base_url,
            model=settings.jev_model,
            api_key=settings.jev_api_key.get_secret_value(),
            timeout_s=settings.jev_timeout_s,
        )
    return MockDecisionProvider("mock-judge")


def build_router(settings: Settings, judge: DecisionProvider | None = None) -> Router:
    rules = RuleRouter(
        RouterConfig(
            long_prompt_chars=settings.router_long_prompt_chars,
            frontier_keywords=settings.router_frontier_keywords,
            default_confidence=settings.router_default_confidence,
        )
    )
    if settings.router_mode == "rules":
        return rules  # the judge is not even constructed, so no call can be made
    return HybridRouter(
        rules,
        judge or build_judge(settings),
        HybridConfig(
            promote_threshold=settings.router_promote_threshold,
            judge_only=settings.router_mode == "judge_only",
            policy=get_policy(settings.router_policy),
        ),
    )


def build_pipeline(
    settings: Settings, registry: ProviderRegistry, judge: DecisionProvider | None = None
) -> Pipeline:
    return Pipeline(
        guard=InputGuard(
            InputGuardConfig(
                max_input_chars=settings.guard_max_input_chars,
                block_injection=settings.guard_block_injection,
            )
        ),
        router=build_router(settings, judge),
        judge_price=Price(settings.jev_price_in_per_mtok, settings.jev_price_out_per_mtok),
        providers=registry,
        prices={
            "small": Price(settings.small_price_in_per_mtok, settings.small_price_out_per_mtok),
            "frontier": Price(
                settings.frontier_price_in_per_mtok, settings.frontier_price_out_per_mtok
            ),
        },
        max_output_tokens=settings.max_output_tokens,
        store_content=settings.trace_store_content,
    )
