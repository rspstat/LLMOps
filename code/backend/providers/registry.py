from collections.abc import Mapping
from dataclasses import dataclass

from providers.base import Provider


@dataclass(frozen=True, slots=True)
class Candidate:
    """One provider to try for a request. `route` is the route it normally serves (None for the
    optional last-resort provider), which decides the price its tokens are billed at."""

    provider: Provider
    route: str | None


@dataclass(frozen=True, slots=True)
class ProviderRegistry:
    """Maps a route name to the provider serving it.

    If the routed provider fails, the request moves to the other routes' providers, so a dead
    small model is covered by the frontier model and vice versa. `fallback` is an optional last
    resort tried after all of them; the production wiring leaves it unset so that a request is
    never answered by a stand-in that is not a real model.
    """

    routes: Mapping[str, Provider]
    fallback: Provider | None = None

    def for_route(self, route: str) -> Provider:
        return self.routes[route]

    def failover_chain(self, route: str) -> list[Candidate]:
        """The routed provider first, then the other routes' providers, then `fallback`.

        A provider object registered for several routes (or as the fallback) appears once.
        """
        chain = [Candidate(self.routes[route], route)]
        chain += [Candidate(p, name) for name, p in self.routes.items() if name != route]
        if self.fallback is not None:
            chain.append(Candidate(self.fallback, None))

        unique: list[Candidate] = []
        for candidate in chain:
            if all(candidate.provider is not seen.provider for seen in unique):
                unique.append(candidate)
        return unique
