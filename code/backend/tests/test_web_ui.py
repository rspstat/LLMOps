import pytest
from fastapi.testclient import TestClient

from gateway.app import create_app
from gateway.settings import Settings

INDEX = (
    '<!doctype html><script src="/theme-init.js"></script>'
    '<script type="module" src="/assets/app.js"></script>'
)
BODY = {"messages": [{"role": "user", "content": "hi"}]}


@pytest.fixture
def built(tmp_path):
    """A stand-in for `npm run build` output."""
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text(INDEX, encoding="utf-8")
    (tmp_path / "theme-init.js").write_text("document.title = 'x'", encoding="utf-8")
    (tmp_path / "assets" / "app.js").write_text("console.log('web')", encoding="utf-8")
    (tmp_path / "private.txt").write_text("not part of the page", encoding="utf-8")
    return tmp_path


def make_client(settings, trace_store, web_dir, **overrides) -> TestClient:
    settings = Settings(_env_file=None, **{**settings.model_dump(), **overrides})
    return TestClient(create_app(settings, trace_store=trace_store, web_dir=web_dir))


def test_page_is_open_without_a_key(settings, trace_store, built):
    client = make_client(settings, trace_store, built)
    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert response.text == INDEX
    assert response.headers["X-Request-ID"]


def test_head_request_works_like_get(settings, trace_store, built):
    client = make_client(settings, trace_store, built)
    response = client.head("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")


@pytest.mark.parametrize("path", ["/", "/theme-init.js", "/assets/app.js"])
def test_every_page_file_carries_a_strict_content_security_policy(
    settings, trace_store, built, path
):
    client = make_client(settings, trace_store, built)
    response = client.get(path)

    assert response.status_code == 200
    csp = response.headers["Content-Security-Policy"]
    assert "default-src 'self'" in csp and "script-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "unsafe-inline" not in csp and "unsafe-eval" not in csp
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_scripts_are_served_as_javascript(settings, trace_store, built):
    client = make_client(settings, trace_store, built)

    assert "javascript" in client.get("/theme-init.js").headers["content-type"]
    assert "javascript" in client.get("/assets/app.js").headers["content-type"]


def test_only_the_files_the_page_needs_are_exposed(settings, trace_store, built):
    client = make_client(settings, trace_store, built)

    assert client.get("/private.txt").status_code == 404
    assert client.get("/assets/../private.txt").status_code == 404
    assert client.get("/assets/nope.js").json()["error"]["code"] == "not_found"


def test_api_stays_protected_while_the_page_is_open(settings, trace_store, built):
    client = make_client(settings, trace_store, built)

    assert client.get("/").status_code == 200
    assert client.post("/v1/chat/completions", json=BODY).status_code == 401


def test_serving_the_page_at_the_root_keeps_the_api_error_behaviour(settings, trace_store, built):
    client = make_client(settings, trace_store, built)

    wrong_method = client.get("/v1/chat/completions")
    assert wrong_method.status_code == 405
    assert "POST" in wrong_method.headers["Allow"]
    assert wrong_method.json()["error"]["code"] == "method_not_allowed"

    unknown = client.get("/v1/nope")
    assert unknown.status_code == 404
    assert unknown.json()["error"]["code"] == "not_found"
    assert client.get("/healthz").json() == {"status": "ok"}


def test_unbuilt_frontend_answers_with_a_hint(settings, trace_store, tmp_path):
    client = make_client(settings, trace_store, tmp_path / "missing")
    response = client.get("/")

    assert response.status_code == 503
    assert "npm run build" in response.text
    assert client.get("/healthz").status_code == 200  # the API itself is unaffected


def test_web_ui_can_be_switched_off(settings, trace_store, built):
    client = make_client(settings, trace_store, built, web_ui_enabled=False)
    response = client.get("/")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
    assert client.get("/assets/app.js").status_code == 404
    assert client.get("/theme-init.js").status_code == 404
