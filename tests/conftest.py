import pytest

from gateway.settings import Settings

TEST_API_KEY = "test-key"


@pytest.fixture
def settings() -> Settings:
    # _env_file=None: never read a real .env during tests.
    return Settings(_env_file=None, gateway_api_key=TEST_API_KEY)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {TEST_API_KEY}"}
