import pytest
from fastapi.testclient import TestClient

from gateway.app import create_app
from gateway.settings import Settings

INDEX = '<!doctype html><script type="module" src="/demo/assets/app.js"></script>'


@pytest.fixture
def built(tmp_path):
    """A stand-in for `npm run build` output."""
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text(INDEX, encoding="utf-8")
    (tmp_path / "assets" / "app.js").write_text("console.log('demo')", encoding="utf-8")
    return tmp_path


def make_client(settings, trace_store, demo_dir, **overrides) -> TestClient:
    settings = Settings(_env_file=None, **{**settings.model_dump(), **overrides})
    return TestClient(create_app(settings, trace_store=trace_store, demo_dir=demo_dir))


def test_demo_page_is_open_without_a_key(settings, trace_store, built):
    client = make_client(settings, trace_store, built)
    response = client.get("/demo/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert response.text == INDEX
    assert response.headers["X-Request-ID"]


def test_demo_path_without_slash_still_reaches_the_page(settings, trace_store, built):
    client = make_client(settings, trace_store, built)

    assert client.get("/demo").text == INDEX


def test_demo_responses_carry_a_strict_content_security_policy(settings, trace_store, built):
    client = make_client(settings, trace_store, built)
    for path in ("/demo/", "/demo/assets/app.js"):
        response = client.get(path)

        assert response.status_code == 200
        csp = response.headers["Content-Security-Policy"]
        assert "default-src 'self'" in csp and "script-src 'self'" in csp
        assert "frame-ancestors 'none'" in csp
        assert "unsafe-inline" not in csp and "unsafe-eval" not in csp
        assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_api_stays_protected_while_the_demo_is_open(settings, trace_store, built):
    client = make_client(settings, trace_store, built)
    body = {"messages": [{"role": "user", "content": "hi"}]}

    assert client.get("/demo/").status_code == 200
    assert client.post("/v1/chat/completions", json=body).status_code == 401


def test_missing_asset_is_an_openai_shaped_404(settings, trace_store, built):
    client = make_client(settings, trace_store, built)
    response = client.get("/demo/assets/nope.js")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_unbuilt_frontend_answers_with_a_hint(settings, trace_store, tmp_path):
    client = make_client(settings, trace_store, tmp_path / "missing")
    for path in ("/demo", "/demo/", "/demo/assets/app.js"):
        response = client.get(path)

        assert response.status_code == 503
        assert "npm run build" in response.text


def test_demo_can_be_switched_off(settings, trace_store, built):
    client = make_client(settings, trace_store, built, demo_ui_enabled=False)
    response = client.get("/demo/")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
