from dataclasses import dataclass
from enum import StrEnum


class Route(StrEnum):
    SMALL = "small"
    FRONTIER = "frontier"


@dataclass(frozen=True, slots=True)
class RouteDecision:
    route: Route
    reason: str
    # 1.0 when an explicit rule fired; lower when the route is only a default. Stage 2 will
    # promote low-confidence decisions to a stronger model.
    confidence: float
