from dataclasses import dataclass

from router.base import Route, RouteDecision

DEFAULT_FRONTIER_KEYWORDS: tuple[str, ...] = (
    "step by step",
    "prove",
    "analyze",
    "architecture",
    "refactor",
    "debug",
    "단계별",
    "증명",
    "분석",
    "설계",
    "리팩터링",
    "디버깅",
)


@dataclass(frozen=True, slots=True)
class RouterConfig:
    long_prompt_chars: int = 600
    frontier_keywords: tuple[str, ...] = DEFAULT_FRONTIER_KEYWORDS
    default_confidence: float = 0.5


class RuleRouter:
    """Stage-1 router: cheap deterministic rules only (no Jev / model-based judgement yet)."""

    def __init__(self, config: RouterConfig | None = None) -> None:
        self.config = config or RouterConfig()

    def decide(self, text: str) -> RouteDecision:
        if len(text) >= self.config.long_prompt_chars:
            return RouteDecision(Route.FRONTIER, "long_prompt", 1.0)
        lowered = text.casefold()
        for keyword in self.config.frontier_keywords:
            if keyword.casefold() in lowered:
                return RouteDecision(Route.FRONTIER, f"keyword:{keyword}", 1.0)
        return RouteDecision(Route.SMALL, "default_small", self.config.default_confidence)

    async def route(self, text: str) -> RouteDecision:
        return self.decide(text)
