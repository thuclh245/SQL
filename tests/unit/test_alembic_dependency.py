import importlib.util
from pathlib import Path


def test_alembic_package_is_available() -> None:
    assert importlib.util.find_spec("alembic") is not None
    assert Path("alembic.ini").exists()
