from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from gateway.middleware import REQUEST_ID_HEADER, RequestIdMiddleware
from gateway.routes import router
from gateway.settings import Settings
from gateway.trace import TraceStore, create_trace_store
from gateway.wiring import build_pipeline, build_registry
from providers.registry import ProviderRegistry


async def _unhandled_error(request: Request, exc: Exception) -> JSONResponse:
    # ServerErrorMiddleware sits outside our middleware, so the header must be added here.
    request_id = request.scope.get("state", {}).get("request_id", "")
    return JSONResponse(
        {"detail": "Internal server error"},
        status_code=500,
        headers={REQUEST_ID_HEADER: request_id},
    )


def create_app(
    settings: Settings | None = None,
    *,
    trace_store: TraceStore | None = None,
    providers: ProviderRegistry | None = None,
) -> FastAPI:
    """Build the gateway. `trace_store` / `providers` let tests inject fakes."""
    settings = settings or Settings()
    app = FastAPI(title="LLMOps Gateway")
    app.state.settings = settings
    app.state.trace_store = trace_store or create_trace_store(settings.database_url)
    app.state.pipeline = build_pipeline(settings, providers or build_registry(settings))
    app.add_middleware(RequestIdMiddleware)
    app.add_exception_handler(Exception, _unhandled_error)
    app.include_router(router)
    return app
