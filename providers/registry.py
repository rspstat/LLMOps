from collections.abc import Mapping
from dataclasses import dataclass

from providers.base import Provider


@dataclass(frozen=True, slots=True)
class ProviderRegistry:
    """Maps a route name to the provider serving it, plus an always-available fallback."""

    routes: Mapping[str, Provider]
    fallback: Provider

    def for_route(self, route: str) -> Provider:
        return self.routes[route]
