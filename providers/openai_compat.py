from typing import Any

import httpx

from providers.base import ProviderError, ProviderRequest, ProviderResponse, estimate_tokens

_ERROR_BODY_LIMIT = 200


class OpenAICompatProvider:
    """Adapter for any server speaking the OpenAI `/chat/completions` protocol.

    Covers vLLM / local SLM servers and OpenAI itself. Anthropic and Google native APIs are not
    OpenAI-compatible and need their own adapters.
    """

    def __init__(
        self,
        name: str,
        *,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout_s: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.name = name
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._model = model
        self._api_key = api_key
        self._timeout_s = timeout_s
        self._transport = transport

    async def complete(self, request: ProviderRequest) -> ProviderResponse:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "max_tokens": request.max_tokens,
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature

        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
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
        return self._parse(response, request)

    def _parse(self, response: httpx.Response, request: ProviderRequest) -> ProviderResponse:
        try:
            data = response.json()
            choice = data["choices"][0]
            content = choice["message"]["content"]
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
