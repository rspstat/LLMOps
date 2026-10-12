from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, loaded from environment variables and `.env`.

    Tests must build this with `_env_file=None` so a developer's real `.env` never leaks in.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Clients must send this as a Bearer token. Empty means every protected call is rejected.
    gateway_api_key: SecretStr = SecretStr("")
