import time

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from gateway.auth import require_api_key
from gateway.pipeline import Blocked, Completed, ProviderUnavailableError
from gateway.schemas import ChatCompletionRequest, error_body
from gateway.trace import TraceRecorder, flush_trace
from providers.base import ChatMessage

router = APIRouter()


def _header_token(value: object) -> str | None:
    """A printable-ASCII header value, or None if it is not one (e.g. a Korean keyword)."""
    text = str(value)
    return text if text.isascii() and text.isprintable() else None


def _route_headers(outcome: Completed, recorder: TraceRecorder) -> dict[str, str]:
    """What the gateway decided, for clients that cannot read the trace.

    `X-LLMOps-Route` is the router's choice; when `X-LLMOps-Fallback` is true a different
    provider answered, and the body's `model` says which. The reason keeps only the part before
    ':' (`keyword:analyze` -> `keyword`) so matched user text never reaches a header.
    `X-LLMOps-Cost-USD` is the whole request: judge call plus every provider attempt.
    """
    headers = {
        "X-LLMOps-Route": outcome.route.route.value,
        "X-LLMOps-Fallback": "true" if outcome.fallback_used else "false",
        "X-LLMOps-Cost-USD": f"{sum(e.cost_usd or 0.0 for e in recorder.events):.8f}",
    }
    reason = _header_token(outcome.route.reason.split(":", 1)[0])
    if reason:
        headers["X-LLMOps-Route-Reason"] = reason
    p_easy = outcome.route.detail.get("p_easy")
    if isinstance(p_easy, int | float):
        headers["X-LLMOps-P-Easy"] = f"{p_easy:.4f}"
    return headers


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/v1/chat/completions", dependencies=[Depends(require_api_key)])
async def chat_completions(body: ChatCompletionRequest, request: Request) -> JSONResponse:
    if body.stream:
        return JSONResponse(
            error_body(
                "Streaming is not supported yet", "invalid_request_error", "stream_unsupported"
            ),
            status_code=400,
        )

    request_id: str = request.state.request_id
    recorder = TraceRecorder(request_id)
    messages = [ChatMessage(m.role, m.content) for m in body.messages]
    try:
        outcome = await request.app.state.pipeline.run(
            recorder,
            messages,
            max_tokens=body.max_tokens,
            temperature=body.temperature,
            client_request_id=request.state.client_request_id,
        )
    except ProviderUnavailableError:
        return JSONResponse(
            error_body("Upstream model unavailable", "upstream_error", "provider_unavailable"),
            status_code=502,
        )
    finally:
        await flush_trace(request.app.state.trace_store, recorder)

    if isinstance(outcome, Blocked):
        # Only the category is returned; the exact rule that fired stays in the trace.
        category = outcome.guard.reason.split(":", 1)[0]
        return JSONResponse(
            error_body(
                f"Request blocked by input guard ({category})",
                "invalid_request_error",
                "input_blocked",
            ),
            status_code=400,
        )

    response = outcome.response
    return JSONResponse(
        headers=_route_headers(outcome, recorder),
        content={
            "id": f"chatcmpl-{request_id}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": response.model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": response.content},
                    "finish_reason": response.finish_reason,
                }
            ],
            "usage": {
                "prompt_tokens": response.prompt_tokens,
                "completion_tokens": response.completion_tokens,
                "total_tokens": response.prompt_tokens + response.completion_tokens,
            },
        },
    )
