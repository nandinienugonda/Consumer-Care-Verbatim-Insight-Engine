import pytest
from pydantic import SecretStr

from ccvie.config import Settings

DEV_SECRET = "test-secret-that-is-at-least-32-characters-long"


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--require-db",
        action="store_true",
        help="fail instead of skip when PostgreSQL is unreachable (use in CI)",
    )


@pytest.fixture
def require_db(request: pytest.FixtureRequest) -> bool:
    return bool(request.config.getoption("--require-db"))


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def dev_settings() -> Settings:
    return Settings(
        _env_file=None,
        auth_dev_mode=True,
        auth_dev_secret=SecretStr(DEV_SECRET),
        otel_exporter_otlp_endpoint=None,
    )
