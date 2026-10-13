from typing import Any

import httpx

from providers.base import ProviderError, estimate_tokens
from providers.decision import ChoiceDecision, ChoiceQuestion, validate_decision

_ERROR_BODY_LIMIT = 200


class JevProvider:
    """Adapter for TypeSafe's Jev ("System One") decision API.

    The request/response shape follows third-party documentation (LiteLLM, DigitalOcean), not an
    official reference, and has not been verified against a live key yet: `state` + `questions`
    in, `answers.<key>.{choice, probabilities, confidence}` and `usage` out. `url` is the full
    endpoint (e.g. `https://api.typesafe.ai/v1/systemone`); gateways such as DigitalOcean use a
    different host and model name, so both come from settings.
    """

    def __init__(
        self,
        name: str = "jev",
        *,
        url: str,
        model: str,
        api_key: str,
        timeout_s: float = 5.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.name = name
        self._url = url
        self._model = model
        self._api_key = api_key
        self._timeout_s = timeout_s
        self._transport = transport

    async def decide(self, state: str, question: ChoiceQuestion) -> ChoiceDecision:
        payload = {
            "model": self._model,
            "state": state,
            "questions": {
                question.key: {
                    "type": "choice",
                    "instructions": question.instructions,
                    "criteria": dict(question.criteria),
                }
            },
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_s, transport=self._transport
            ) as client:
                response = await client.post(self._url, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise ProviderError(f"{self.name}: request failed ({type(exc).__name__})") from exc

        if response.status_code >= 400:
            body = response.text[:_ERROR_BODY_LIMIT]
            raise ProviderError(f"{self.name}: HTTP {response.status_code}: {body}")
        return validate_decision(self._parse(response, state, question), question)

    def _parse(
        self, response: httpx.Response, state: str, question: ChoiceQuestion
    ) -> ChoiceDecision:
        try:
            data = response.json()
            answer = data["answers"][question.key]
            if answer["type"] != "choice":
                raise TypeError("not a choice answer")
            choice = answer["choice"]
            probabilities = answer["probabilities"]
            if not isinstance(choice, str) or not isinstance(probabilities, dict):
                raise TypeError("unexpected answer shape")
        except (ValueError, KeyError, TypeError) as exc:
            raise ProviderError(f"{self.name}: malformed response") from exc

        confidence = answer.get("confidence")
        if not isinstance(confidence, int | float) or isinstance(confidence, bool):
            confidence = probabilities.get(choice)
        if not isinstance(confidence, int | float) or isinstance(confidence, bool):
            raise ProviderError(f"{self.name}: malformed response")

        usage: dict[str, Any] = data.get("usage") or {}
        input_tokens = usage.get("input_tokens")
        output_tokens = usage.get("output_tokens")
        return ChoiceDecision(
            choice=choice,
            probabilities=probabilities,
            confidence=float(confidence),
            model=str(data.get("model") or self._model),
            input_tokens=input_tokens if isinstance(input_tokens, int) else estimate_tokens(state),
            output_tokens=output_tokens if isinstance(output_tokens, int) else 1,
        )
