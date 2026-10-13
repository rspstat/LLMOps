from collections.abc import Sequence

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from gateway.middleware import REQUEST_ID_HEADER
from gateway.schemas import error_body

_HTTP_ERROR_CODES = {401: "invalid_api_key", 404: "not_found", 405: "method_not_allowed"}
_MAX_REPORTED_ERRORS = 3


def _param(loc: Sequence[str | int]) -> str | None:
    """`("body", "messages", 0, "role")` -> `messages[0].role`; the leading "body" is dropped.

    A location that starts with a number is not a field (invalid JSON reports the character
    offset), so it has no param.
    """
    parts = loc[1:] if loc and loc[0] == "body" else loc
    if parts and isinstance(parts[0], int):
        return None
    path = ""
    for part in parts:
        if isinstance(part, int):
            path += f"[{part}]"
        else:
            path += f".{part}" if path else str(part)
    return path or None


async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Authentication failures, unknown paths, wrong methods: in the OpenAI `error` shape."""
    message = exc.detail if isinstance(exc.detail, str) else "Request failed"
    error_type = "server_error" if exc.status_code >= 500 else "invalid_request_error"
    code = _HTTP_ERROR_CODES.get(exc.status_code, "http_error")
    return JSONResponse(
        error_body(message, error_type, code), status_code=exc.status_code, headers=exc.headers
    )


async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Only the field path and the rule's message are returned, never the offending input value."""
    errors = exc.errors()
    problems = []
    for error in errors[:_MAX_REPORTED_ERRORS]:
        param = _param(error["loc"])
        problems.append(f"{param}: {error['msg']}" if param else error["msg"])
    first_param = _param(errors[0]["loc"]) if errors else None
    return JSONResponse(
        error_body("; ".join(problems), "invalid_request_error", "invalid_request", first_param),
        status_code=422,
    )


async def _unhandled_error(request: Request, exc: Exception) -> JSONResponse:
    # ServerErrorMiddleware sits outside our middleware, so the header must be added here.
    request_id = request.scope.get("state", {}).get("request_id", "")
    return JSONResponse(
        error_body("Internal server error", "server_error", "internal_error"),
        status_code=500,
        headers={REQUEST_ID_HEADER: request_id},
    )


def register_error_handlers(app: FastAPI) -> None:
    """Make every error response the OpenAI shape: `{"error": {message, type, param, code}}`."""
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(Exception, _unhandled_error)
