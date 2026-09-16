import pytest

from t2s.configuration.settings import Settings


@pytest.fixture(autouse=True)
def _isolate_local_env_file(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure test runs are hermetic and not contaminated by a local .env file."""
    monkeypatch.setitem(Settings.model_config, "env_file", None)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
