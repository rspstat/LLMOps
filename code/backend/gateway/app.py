from pathlib import Path

from fastapi import FastAPI

from gateway.errors import register_error_handlers
from gateway.middleware import RequestIdMiddleware
from gateway.routes import router
from gateway.settings import Settings
from gateway.trace import TraceStore, create_trace_store
from gateway.web import DEFAULT_WEB_DIR, register_web_ui
from gateway.wiring import build_pipeline, build_registry
from providers.decision import DecisionProvider
from providers.registry import ProviderRegistry


def create_app(
    settings: Settings | None = None,
    *,
    trace_store: TraceStore | None = None,
    providers: ProviderRegistry | None = None,
    judge: DecisionProvider | None = None,
    web_dir: Path = DEFAULT_WEB_DIR,
) -> FastAPI:
    """Build the gateway. `trace_store`, `providers`, `judge`, `web_dir` let tests inject fakes."""
    settings = settings or Settings()
    app = FastAPI(title="LLMOps Gateway")
    app.state.settings = settings
    app.state.trace_store = trace_store or create_trace_store(settings.database_url)
    app.state.pipeline = build_pipeline(settings, providers or build_registry(settings), judge)
    app.add_middleware(RequestIdMiddleware)
    register_error_handlers(app)
    app.include_router(router)
    if settings.web_ui_enabled:
        register_web_ui(app, web_dir)
    return app
