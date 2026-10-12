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
    # Stage-2 features stay off until explicitly enabled.
    assert settings.router_mode == "rules" and settings.judge_provider == "mock"
    assert settings.jev_api_key.get_secret_value() == ""


def test_secrets_are_masked_in_repr():
    settings = Settings(_env_file=None, gateway_api_key="top-secret", openai_api_key="sk-secret")
    assert "top-secret" not in repr(settings) and "sk-secret" not in repr(settings)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"small_provider": "slm", "slm_api_key": "slm-secret-xyz"},  # no model
        {"frontier_provider": "openai", "openai_api_key": "openai-secret-xyz"},  # no model
        {
            "judge_provider": "jev",
            "jev_api_key": "",
            "openai_api_key": "other-secret-xyz",
        },  # no key
        {"router_promote_threshold": 5, "jev_api_key": "jev-secret-xyz"},  # out of range
    ],
)
def test_a_validation_error_never_prints_the_raw_input(kwargs):
    # pydantic's default error text embeds the whole input dict, API keys included.
    with pytest.raises(ValidationError) as info:
        Settings(_env_file=None, **kwargs)
    text = str(info.value)
    assert "validation error" in text and "secret-xyz" not in text


def test_slm_api_key_is_optional_and_masked():
    assert Settings(_env_file=None).slm_api_key.get_secret_value() == ""
    hosted = Settings(_env_file=None, small_provider="slm", slm_model="m", slm_api_key="slm-secret")
    assert "slm-secret" not in repr(hosted)


def test_slm_provider_requires_a_model():
    with pytest.raises(ValidationError, match="SLM_MODEL"):
        Settings(_env_file=None, small_provider="slm")


def test_openai_frontier_requires_model_and_key():
    with pytest.raises(ValidationError, match="FRONTIER_MODEL"):
        Settings(_env_file=None, frontier_provider="openai", openai_api_key="k")
    with pytest.raises(ValidationError, match="OPENAI_API_KEY"):
        Settings(_env_file=None, frontier_provider="openai", frontier_model="m")


def test_jev_judge_requires_a_key_and_masks_it():
    with pytest.raises(ValidationError, match="JEV_API_KEY"):
        Settings(_env_file=None, judge_provider="jev")
    settings = Settings(_env_file=None, judge_provider="jev", jev_api_key="jev-secret")
    assert "jev-secret" not in repr(settings)


def test_router_mode_and_threshold_are_validated():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, router_mode="always-jev")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, router_promote_threshold=1.5)
    assert Settings(_env_file=None, router_mode="judge_only").router_mode == "judge_only"


def test_keywords_can_be_overridden_from_environment(monkeypatch):
    monkeypatch.setenv("ROUTER_FRONTIER_KEYWORDS", '["sql","regex"]')
    assert Settings(_env_file=None).router_frontier_keywords == ("sql", "regex")
