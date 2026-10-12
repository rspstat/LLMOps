import pytest
from pydantic import ValidationError

from gateway.settings import Settings
from router.rule_router import DEFAULT_FRONTIER_KEYWORDS


def test_env_example_loads_and_is_safe_by_default():
    # `cp .env.example .env` must yield a working, offline, content-free configuration.
    settings = Settings(_env_file=".env.example")
    assert settings.small_provider == "mock" and settings.frontier_provider == "mock"
    assert settings.database_url.startswith("sqlite:///")
    assert settings.trace_store_content is False
    assert settings.router_frontier_keywords == DEFAULT_FRONTIER_KEYWORDS
    assert settings.gateway_api_key.get_secret_value() == ""


def test_secrets_are_masked_in_repr():
    settings = Settings(_env_file=None, gateway_api_key="top-secret", openai_api_key="sk-secret")
    assert "top-secret" not in repr(settings) and "sk-secret" not in repr(settings)


def test_slm_provider_requires_a_model():
    with pytest.raises(ValidationError, match="SLM_MODEL"):
        Settings(_env_file=None, small_provider="slm")


def test_openai_frontier_requires_model_and_key():
    with pytest.raises(ValidationError, match="FRONTIER_MODEL"):
        Settings(_env_file=None, frontier_provider="openai", openai_api_key="k")
    with pytest.raises(ValidationError, match="OPENAI_API_KEY"):
        Settings(_env_file=None, frontier_provider="openai", frontier_model="m")


def test_keywords_can_be_overridden_from_environment(monkeypatch):
    monkeypatch.setenv("ROUTER_FRONTIER_KEYWORDS", '["sql","regex"]')
    assert Settings(_env_file=None).router_frontier_keywords == ("sql", "regex")
