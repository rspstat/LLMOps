import pytest

from gateway.settings import Settings
from gateway.trace import SqliteTraceStore

TEST_API_KEY = "test-key"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def settings(tmp_path) -> Settings:
    # _env_file=None: never read a real .env during tests. The trace DB lives in tmp_path.
    return Settings(
        _env_file=None,
        gateway_api_key=TEST_API_KEY,
        database_url=f"sqlite:///{(tmp_path / 'traces.sqlite3').as_posix()}",
    )


@pytest.fixture
def trace_store(tmp_path) -> SqliteTraceStore:
    return SqliteTraceStore(tmp_path / "e2e.sqlite3")


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {TEST_API_KEY}"}
