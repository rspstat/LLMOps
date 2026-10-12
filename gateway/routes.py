import time

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from gateway.auth import require_api_key
from gateway.pipeline import Blocked, ProviderUnavailableError
from gateway.schemas import ChatCompletionRequest, error_body
from gateway.trace import TraceRecorder, flush_trace
from providers.base import ChatMessage

router = APIRouter()


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
        {
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
        }
    )
