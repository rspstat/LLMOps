from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, PlainTextResponse
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

# code/backend/gateway/web.py -> code/frontend/dist (the output of `npm run build`)
DEFAULT_WEB_DIR = Path(__file__).resolve().parents[2] / "frontend" / "dist"

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
_NOT_BUILT = "The web UI is not built yet.\nRun: cd code/frontend && npm ci && npm run build\n"


class _AssetFiles(StaticFiles):
    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        response.headers.update(_SECURITY_HEADERS)
        return response


def register_web_ui(app: FastAPI, web_dir: Path = DEFAULT_WEB_DIR) -> None:
    """Serve the built React page at `/`, or a short hint if it has not been built.

    Only the files the page needs are exposed (`/`, `/theme-init.js`, `/assets/*`) instead of
    mounting the whole folder at the root: a catch-all mount would answer API paths with its
    own 404 and hide the 405 (with an `Allow` header) that the real routes give.
    """
    index = web_dir / "index.html"
    if not index.is_file():

        async def not_built() -> PlainTextResponse:
            return PlainTextResponse(_NOT_BUILT, status_code=503)

        app.add_api_route("/", not_built, methods=["GET", "HEAD"], include_in_schema=False)
        return

    async def home() -> FileResponse:
        return FileResponse(index, headers=_SECURITY_HEADERS)

    app.add_api_route("/", home, methods=["GET", "HEAD"], include_in_schema=False)

    theme_init = web_dir / "theme-init.js"
    if theme_init.is_file():

        async def theme_script() -> FileResponse:
            return FileResponse(theme_init, headers=_SECURITY_HEADERS)

        app.add_api_route(
            "/theme-init.js", theme_script, methods=["GET", "HEAD"], include_in_schema=False
        )

    if (web_dir / "assets").is_dir():
        app.mount("/assets", _AssetFiles(directory=web_dir / "assets"), name="assets")
