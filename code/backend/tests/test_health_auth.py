import pytest
from fastapi import Depends, Request
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


def test_request_id_is_server_generated_even_if_client_sends_one(client):
    # The ID is the trace key; honouring client values would allow collisions and forgery.
    headers = {"X-Request-ID": "abc-123_ok.1"}
    first = client.get("/healthz", headers=headers).headers["X-Request-ID"]
    second = client.get("/healthz", headers=headers).headers["X-Request-ID"]
    assert "abc-123_ok.1" not in (first, second)
    assert first != second


def test_client_request_id_is_kept_for_correlation_only_if_safe(app):
    seen: list[str | None] = []

    @app.get("/whoami")
    async def whoami(request: Request) -> None:
        seen.append(request.state.client_request_id)

    client = TestClient(app)
    client.get("/whoami", headers={"X-Request-ID": "abc-123_ok.1"})
    client.get("/whoami", headers={"X-Request-ID": "has space"})
    client.get("/whoami", headers={"X-Request-ID": "x" * 65})
    client.get("/whoami")
    assert seen == ["abc-123_ok.1", None, None, None]


def test_protected_route_requires_bearer_key(client, auth_headers):
    assert client.get("/protected").status_code == 401
    assert client.get("/protected", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get("/protected", headers={"Authorization": "test-key"}).status_code == 401
    assert client.get("/protected", headers=auth_headers).status_code == 200


def test_unauthorized_response_still_carries_request_id(client):
    response = client.get("/protected")
    assert response.status_code == 401
    assert response.headers["X-Request-ID"]


def test_empty_configured_key_rejects_everything(settings):
    app = create_app(
        Settings(_env_file=None, gateway_api_key="", database_url=settings.database_url)
    )

    @app.get("/protected", dependencies=[Depends(require_api_key)])
    async def protected() -> None: ...

    client = TestClient(app)
    assert client.get("/protected", headers={"Authorization": "Bearer "}).status_code == 401


def test_unhandled_error_returns_500_with_request_id(client):
    response = client.get("/boom")
    assert response.status_code == 500
    assert response.headers["X-Request-ID"]
