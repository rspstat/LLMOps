from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

# code/backend/gateway/demo.py -> code/frontend/dist (the output of `npm run build`)
DEFAULT_DEMO_DIR = Path(__file__).resolve().parents[2] / "frontend" / "dist"
DEMO_PATH = "/demo"

# Everything the page loads comes from this origin, and nothing inline runs. The page renders
# model output, which is untrusted text, so scripts and framing are locked down as well.
_SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
        "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
}
_NOT_BUILT = "The demo screen is not built yet.\nRun: cd code/frontend && npm ci && npm run build\n"


class _DemoFiles(StaticFiles):
    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        response.headers.update(_SECURITY_HEADERS)
        return response


def register_demo_ui(app: FastAPI, demo_dir: Path = DEFAULT_DEMO_DIR) -> None:
    """Serve the built React screen at /demo, or a short hint if it has not been built."""
    if (demo_dir / "index.html").is_file():
        app.mount(DEMO_PATH, _DemoFiles(directory=demo_dir, html=True), name="demo")
        return

    async def not_built() -> PlainTextResponse:
        return PlainTextResponse(_NOT_BUILT, status_code=503)

    app.add_api_route(DEMO_PATH, not_built, include_in_schema=False)
    app.add_api_route(DEMO_PATH + "/{rest:path}", not_built, include_in_schema=False)
