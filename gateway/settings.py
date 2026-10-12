from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from router.rule_router import DEFAULT_FRONTIER_KEYWORDS


class Settings(BaseSettings):
    """Runtime configuration, loaded from environment variables and `.env`.

    Tests must build this with `_env_file=None` so a developer's real `.env` never leaks in.
    Guard / router thresholds and prices live here, not in code, because the evaluation module
    sweeps them.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Clients must send this as a Bearer token. Empty means every protected call is rejected.
    gateway_api_key: SecretStr = SecretStr("")
    max_output_tokens: int = 1024

    # Trace storage. Only sqlite:/// is implemented; postgresql:// is planned.
    database_url: str = "sqlite:///./data/traces.sqlite3"
    # Off by default: the repo is public and prompts may contain personal data.
    trace_store_content: bool = False

    # Input guard
    guard_max_input_chars: int = 8000
    guard_block_injection: bool = True

    # Router
    router_long_prompt_chars: int = 600
    router_frontier_keywords: tuple[str, ...] = DEFAULT_FRONTIER_KEYWORDS
    router_default_confidence: float = 0.5

    # Providers. Both default to the offline mock, so keys in `.env` never cause real calls
    # unless these are changed explicitly.
    small_provider: Literal["mock", "slm"] = "mock"
    frontier_provider: Literal["mock", "openai"] = "mock"
    provider_timeout_s: float = 30.0
    slm_base_url: str = "http://localhost:8001/v1"
    slm_model: str = ""
    frontier_base_url: str = "https://api.openai.com/v1"
    frontier_model: str = ""
    openai_api_key: SecretStr = SecretStr("")

    # USD per 1M tokens, per route (0 for mock / self-hosted).
    small_price_in_per_mtok: float = 0.0
    small_price_out_per_mtok: float = 0.0
    frontier_price_in_per_mtok: float = 0.0
    frontier_price_out_per_mtok: float = 0.0

    @model_validator(mode="after")
    def _real_providers_need_their_config(self) -> "Settings":
        if self.small_provider == "slm" and not self.slm_model:
            raise ValueError("SLM_MODEL is required when SMALL_PROVIDER=slm")
        if self.frontier_provider == "openai":
            if not self.frontier_model:
                raise ValueError("FRONTIER_MODEL is required when FRONTIER_PROVIDER=openai")
            if not self.openai_api_key.get_secret_value():
                raise ValueError("OPENAI_API_KEY is required when FRONTIER_PROVIDER=openai")
        return self
