from typing import Any, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from providers.openai_compat import RESERVED_BODY_KEYS
from router.policy import DEFAULT_POLICY_VERSION, get_policy
from router.rule_router import DEFAULT_FRONTIER_KEYWORDS


class Settings(BaseSettings):
    """Runtime configuration, loaded from environment variables and `.env`.

    Tests must build this with `_env_file=None` so a developer's real `.env` never leaks in.
    Guard / router thresholds and prices live here, not in code, because the evaluation module
    sweeps them.
    """

    # hide_input_in_errors: a validation error otherwise prints the raw input, API keys included,
    # into terminals, tracebacks and logs.
    # env_ignore_empty: a blank `NAME=` line means "use the default". Without it a blank number
    # (e.g. `JEV_PRICE_OUT_PER_MTOK=`) fails to parse and the whole configuration refuses to load.
    model_config = SettingsConfigDict(
        env_file=".env", extra="ignore", hide_input_in_errors=True, env_ignore_empty=True
    )

    # Clients must send this as a Bearer token. Empty means every protected call is rejected.
    gateway_api_key: SecretStr = SecretStr("")
    max_output_tokens: int = 1024
    # Serve the built web UI (code/frontend/dist) at `/`. The page holds no secrets; the API
    # calls it makes still need the Bearer key. Turn it off to run the gateway as a pure API.
    web_ui_enabled: bool = True

    # Trace storage. Only sqlite:/// is implemented; postgresql:// is planned.
    database_url: str = "sqlite:///./data/traces.sqlite3"
    # Off by default: the repo is public and prompts may contain personal data.
    trace_store_content: bool = False

    # Input guard
    guard_max_input_chars: int = 8000
    guard_block_injection: bool = True

    # Router. `rules` = stage-1 behaviour (no judge calls); `hybrid` = rule hit is final, otherwise
    # ask the judge; `judge_only` = always ask the judge (to compare it against the rules).
    router_mode: Literal["rules", "hybrid", "judge_only"] = "rules"
    router_long_prompt_chars: int = 600
    router_frontier_keywords: tuple[str, ...] = DEFAULT_FRONTIER_KEYWORDS
    router_default_confidence: float = 0.5
    # The small model needs p(easy) >= this from the judge; otherwise the request is promoted.
    router_promote_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    # Which judge policy wording is sent with every request (router/policy.py). Versions are never
    # edited, so a trace or an evaluation names exactly what the judge was asked.
    router_policy: str = DEFAULT_POLICY_VERSION

    # Judge (closed-set decisions for the router). Defaults to the offline mock, so a Jev key in
    # `.env` is never used unless JUDGE_PROVIDER=jev. JEV_BASE_URL is the full endpoint URL.
    judge_provider: Literal["mock", "jev"] = "mock"
    jev_api_key: SecretStr = SecretStr("")
    jev_base_url: str = "https://api.typesafe.ai/v1/systemone"
    jev_model: str = "jev-latest"
    jev_timeout_s: float = 5.0
    jev_price_in_per_mtok: float = 0.0
    jev_price_out_per_mtok: float = 0.0

    # Providers. Both default to the offline mock, so keys in `.env` never cause real calls
    # unless these are changed explicitly.
    small_provider: Literal["mock", "slm"] = "mock"
    frontier_provider: Literal["mock", "openai"] = "mock"
    provider_timeout_s: float = 30.0
    slm_base_url: str = "http://localhost:8001/v1"
    slm_model: str = ""
    # Empty for a self-hosted server (vLLM, Ollama). Set it when the small model is a hosted API.
    slm_api_key: SecretStr = SecretStr("")
    frontier_base_url: str = "https://api.openai.com/v1"
    frontier_model: str = ""
    openai_api_key: SecretStr = SecretStr("")
    # Vendor-specific JSON fields added to every request of that model, e.g.
    # {"enable_thinking": false} for Qwen. Fields the adapter owns (model, messages) are refused.
    slm_extra_body: dict[str, Any] = Field(default_factory=dict)
    frontier_extra_body: dict[str, Any] = Field(default_factory=dict)

    # USD per 1M tokens, per route (0 for mock / self-hosted).
    small_price_in_per_mtok: float = 0.0
    small_price_out_per_mtok: float = 0.0
    frontier_price_in_per_mtok: float = 0.0
    frontier_price_out_per_mtok: float = 0.0

    @field_validator("router_policy")
    @classmethod
    def _known_policy(cls, value: str) -> str:
        get_policy(value)  # raises ValueError naming the known versions
        return value

    @model_validator(mode="after")
    def _real_providers_need_their_config(self) -> "Settings":
        if self.small_provider == "slm" and not self.slm_model:
            raise ValueError("SLM_MODEL is required when SMALL_PROVIDER=slm")
        if self.frontier_provider == "openai":
            if not self.frontier_model:
                raise ValueError("FRONTIER_MODEL is required when FRONTIER_PROVIDER=openai")
            if not self.openai_api_key.get_secret_value():
                raise ValueError("OPENAI_API_KEY is required when FRONTIER_PROVIDER=openai")
        if self.judge_provider == "jev" and not self.jev_api_key.get_secret_value():
            raise ValueError("JEV_API_KEY is required when JUDGE_PROVIDER=jev")
        for name, extra in (
            ("SLM_EXTRA_BODY", self.slm_extra_body),
            ("FRONTIER_EXTRA_BODY", self.frontier_extra_body),
        ):
            reserved = RESERVED_BODY_KEYS & set(extra)
            if reserved:
                raise ValueError(f"{name} may not set {', '.join(sorted(reserved))}")
        return self
