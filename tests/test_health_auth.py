import pytest
from fastapi import Depends
from fastapi.testclient import TestClient

from gateway.app import create_app
from gateway.auth import require_api_key
from gateway.settings import Settings


@pytest.fixture
def app(settings):
    app = create_app(settings)

    @app.get("/protected", dependencies=[Depends(require_api_key)])
    async def protected() -> dict[str, str]:
        return {"ok": "yes"}

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("boom")

    return app


@pytest.fixture
def client(app):
    return TestClient(app, raise_server_exceptions=False)


def test_healthz_is_open_and_returns_ok(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_request_id_is_generated_when_absent(client):
    first = client.get("/healthz").headers["X-Request-ID"]
    second = client.get("/healthz").headers["X-Request-ID"]
    assert first and second and first != second


def test_valid_client_request_id_is_echoed(client):
    response = client.get("/healthz", headers={"X-Request-ID": "abc-123_ok.1"})
    assert response.headers["X-Request-ID"] == "abc-123_ok.1"


@pytest.mark.parametrize("bad", ["has space", "x" * 65, "semi;colon", "new\tline"])
def test_invalid_client_request_id_is_replaced(client, bad):
    response = client.get("/healthz", headers={"X-Request-ID": bad})
    assert response.headers["X-Request-ID"] != bad
    assert response.headers["X-Request-ID"]


def test_protected_route_requires_bearer_key(client, auth_headers):
    assert client.get("/protected").status_code == 401
    assert client.get("/protected", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get("/protected", headers={"Authorization": "test-key"}).status_code == 401
    assert client.get("/protected", headers=auth_headers).status_code == 200


def test_unauthorized_response_still_carries_request_id(client):
    response = client.get("/protected")
    assert response.status_code == 401
    assert response.headers["X-Request-ID"]


def test_empty_configured_key_rejects_everything():
    app = create_app(Settings(_env_file=None, gateway_api_key=""))

    @app.get("/protected", dependencies=[Depends(require_api_key)])
    async def protected() -> None: ...

    client = TestClient(app)
    assert client.get("/protected", headers={"Authorization": "Bearer "}).status_code == 401


def test_unhandled_error_returns_500_with_request_id(client):
    response = client.get("/boom", headers={"X-Request-ID": "trace-me"})
    assert response.status_code == 500
    assert response.headers["X-Request-ID"] == "trace-me"
