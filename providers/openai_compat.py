from collections.abc import Mapping
from typing import Any

import httpx

from providers.base import ProviderError, ProviderRequest, ProviderResponse, estimate_tokens

_ERROR_BODY_LIMIT = 200

# Fields the adapter decides itself; `extra_body` may not set them.
RESERVED_BODY_KEYS = frozenset(
    {"model", "messages", "max_tokens", "max_completion_tokens", "temperature", "stream"}
)


class OpenAICompatProvider:
    """Adapter for any server speaking the OpenAI `/chat/completions` protocol.

    Covers vLLM / Ollama / local SLM servers and OpenAI itself. Anthropic and Google native APIs
    are not OpenAI-compatible and need their own adapters.

    Some newer hosted models reject `max_tokens` (they want `max_completion_tokens`) or any
    `temperature` other than their default. Such a request fails with a 400 that names the
    parameter and is not billed, so on exactly that signal the request is re-sent once per
    problem with the other form, and the choice is remembered for later calls. Every other error
    (401, 429, 5xx, a 400 that names neither parameter) is raised immediately and never re-sent.

    `extra_body` carries vendor-specific request fields that the OpenAI protocol has no slot for,
    e.g. `{"enable_thinking": false}` for Qwen hybrid models, which otherwise spend a small
    `max_tokens` on hidden reasoning and answer with nothing.
    """

    _MAX_ADAPTATIONS = 2

    def __init__(
        self,
        name: str,
        *,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout_s: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
        extra_body: Mapping[str, Any] | None = None,
    ) -> None:
        reserved = RESERVED_BODY_KEYS & set(extra_body or {})
        if reserved:
            raise ValueError(f"extra_body may not set {', '.join(sorted(reserved))}")
        self.name = name
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._model = model
        self._api_key = api_key
        self._timeout_s = timeout_s
        self._transport = transport
        self._extra_body = dict(extra_body or {})
        self._token_param = "max_tokens"
        self._send_temperature = True

    def _payload(self, request: ProviderRequest) -> dict[str, Any]:
        payload: dict[str, Any] = {
            **self._extra_body,
            "model": self._model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            self._token_param: request.max_tokens,
        }
        if request.temperature is not None and self._send_temperature:
            payload["temperature"] = request.temperature
        return payload

    def _adapt_to(self, error_body: str, request: ProviderRequest) -> bool:
        """Switch to what the server asked for. False if the error names nothing we can change."""
        changed = False
        if self._token_param == "max_tokens" and "max_completion_tokens" in error_body:
            self._token_param = "max_completion_tokens"
            changed = True
        if (
            self._send_temperature
            and request.temperature is not None
            and "temperature" in error_body
        ):
            self._send_temperature = False
            changed = True
        return changed

    async def _post(self, payload: dict[str, Any], headers: dict[str, str]) -> httpx.Response:
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_s, transport=self._transport
            ) as client:
                return await client.post(self._url, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise ProviderError(f"{self.name}: request failed ({type(exc).__name__})") from exc

    async def complete(self, request: ProviderRequest) -> ProviderResponse:
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
        response = await self._post(self._payload(request), headers)
        for _ in range(self._MAX_ADAPTATIONS):
            if response.status_code != 400 or not self._adapt_to(response.text, request):
                break
            response = await self._post(self._payload(request), headers)

        if response.status_code >= 400:
            body = response.text[:_ERROR_BODY_LIMIT]
            raise ProviderError(f"{self.name}: HTTP {response.status_code}: {body}")
        return self._parse(response, request)

    def _parse(self, response: httpx.Response, request: ProviderRequest) -> ProviderResponse:
        try:
            data = response.json()
            choice = data["choices"][0]
            content = choice["message"]["content"]
            if content is None and choice.get("finish_reason") == "length":
                # A reasoning model can spend the whole token budget thinking and return nothing.
                # That is an empty answer (visible as such), not a malformed response.
                content = ""
            if not isinstance(content, str):
                raise TypeError("content is not a string")
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ProviderError(f"{self.name}: malformed response") from exc

        usage = data.get("usage") or {}
        prompt_tokens = usage.get("prompt_tokens")
        completion_tokens = usage.get("completion_tokens")
        if not isinstance(prompt_tokens, int):
            prompt_tokens = sum(estimate_tokens(m.content) for m in request.messages)
        if not isinstance(completion_tokens, int):
            completion_tokens = estimate_tokens(content)

        return ProviderResponse(
            content=content,
            model=str(data.get("model") or self._model),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            finish_reason=str(choice.get("finish_reason") or "stop"),
        )
