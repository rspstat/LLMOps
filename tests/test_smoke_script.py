import json

import httpx
import pytest

from gateway.settings import Settings
from scripts import smoke_live

SECRET = "sk-test-secret-value"


@pytest.fixture
def live_settings() -> Settings:
    return Settings(
        _env_file=None,
        slm_base_url="http://slm.test:8001/v1",
        slm_model="tiny",
        frontier_base_url="https://api.example.test/v1",
        frontier_model="big",
        openai_api_key=SECRET,
    )


@pytest.fixture(autouse=True)
def no_real_network(monkeypatch):
    """Any real HTTP attempt in this module is a test bug."""

    def boom(*args, **kwargs):
        raise AssertionError("smoke script test attempted real network access")

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", boom)


@pytest.mark.parametrize("environ", [{}, {"ALLOW_LIVE_CALLS": "0"}, {"ALLOW_LIVE_CALLS": "true"}])
def test_refuses_without_explicit_flag_and_builds_nothing(
    environ, live_settings, monkeypatch, capsys
):
    def must_not_build(*args, **kwargs):
        raise AssertionError("provider was built without the opt-in flag")

    monkeypatch.setattr(smoke_live, "build_provider", must_not_build)
    code = smoke_live.main(["--target", "slm"], environ, settings=live_settings)
    assert code == smoke_live.EXIT_REFUSED
    assert "ALLOW_LIVE_CALLS=1" in capsys.readouterr().err


def test_target_is_required():
    with pytest.raises(SystemExit):
        smoke_live.main([], {"ALLOW_LIVE_CALLS": "1"})


def test_refuses_when_target_is_not_configured(capsys):
    settings = Settings(_env_file=None)
    code = smoke_live.main(["--target", "frontier"], {"ALLOW_LIVE_CALLS": "1"}, settings=settings)
    assert code == smoke_live.EXIT_REFUSED
    assert "FRONTIER_MODEL" in capsys.readouterr().err


def test_enabled_call_is_capped_and_never_prints_the_api_key(live_settings, capsys):
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        seen["auth"] = request.headers["authorization"]
        body = {
            "model": "big",
            "choices": [{"message": {"content": "hi"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 1},
        }
        return httpx.Response(200, json=body)

    code = smoke_live.main(
        ["--target", "frontier", "--max-tokens", "100000"],
        {"ALLOW_LIVE_CALLS": "1"},
        settings=live_settings,
        transport=httpx.MockTransport(handler),
    )
    out = capsys.readouterr()

    assert code == smoke_live.EXIT_OK
    assert seen["body"]["max_tokens"] == smoke_live.MAX_TOKENS_CAP
    assert seen["auth"] == f"Bearer {SECRET}"
    assert SECRET not in out.out + out.err
    assert "api.example.test" in out.out and "tokens:  prompt=5 completion=1" in out.out


def test_failed_call_exits_nonzero_without_retrying(live_settings, capsys):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(500, text="boom")

    code = smoke_live.main(
        ["--target", "slm"],
        {"ALLOW_LIVE_CALLS": "1"},
        settings=live_settings,
        transport=httpx.MockTransport(handler),
    )
    assert code == smoke_live.EXIT_CALL_FAILED
    assert len(calls) == 1
    assert "HTTP 500" in capsys.readouterr().err
