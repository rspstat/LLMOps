from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from gateway.middleware import REQUEST_ID_HEADER, RequestIdMiddleware
from gateway.routes import router
from gateway.settings import Settings


async def _unhandled_error(request: Request, exc: Exception) -> JSONResponse:
    # ServerErrorMiddleware sits outside our middleware, so the header must be added here.
    request_id = request.scope.get("state", {}).get("request_id", "")
    return JSONResponse(
        {"detail": "Internal server error"},
        status_code=500,
        headers={REQUEST_ID_HEADER: request_id},
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(title="LLMOps Gateway")
    app.state.settings = settings or Settings()
    app.add_middleware(RequestIdMiddleware)
    app.add_exception_handler(Exception, _unhandled_error)
    app.include_router(router)
    return app
