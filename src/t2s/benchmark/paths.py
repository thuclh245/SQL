"""Resolution of machine-specific benchmark database roots.

The BIRD mini-dev databases are large and machine-specific: on each host they
live in a different directory, and the in-repo ``benchmarks/t2s/databases/*``
entries are untracked local symlinks (see ``.gitignore``). To keep the working
tree clean and portable, the roots are resolved through environment variables
with an in-repo default, instead of hardcoding absolute paths or relying on a
committed symlink.

Environment overrides:

* ``T2S_BENCHMARK_OFFICIAL_DB_ROOT`` -- directory holding the 11 populated
  ``<db_id>/<db_id>.sqlite`` execution databases.
* ``T2S_BENCHMARK_SCHEMA_ONLY_ROOT`` -- directory holding the schema-only
  placeholder databases (no data rows).

When unset, both fall back to the in-repo location, which on a developer
machine is a local symlink into the populated dataset.
"""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]

OFFICIAL_DB_ROOT_ENV = "T2S_BENCHMARK_OFFICIAL_DB_ROOT"
SCHEMA_ONLY_DB_ROOT_ENV = "T2S_BENCHMARK_SCHEMA_ONLY_ROOT"

_DEFAULT_OFFICIAL_DB_ROOT = PROJECT_ROOT / "benchmarks" / "t2s" / "databases" / "official"
_DEFAULT_SCHEMA_ONLY_DB_ROOT = (
    PROJECT_ROOT / "benchmarks" / "t2s" / "databases" / "schema_only_placeholders"
)


def official_database_root() -> Path:
    """Return the populated (official) benchmark database root.

    Honors ``T2S_BENCHMARK_OFFICIAL_DB_ROOT`` when set, otherwise the in-repo
    default. Read from ``os.environ`` on each call so tests and scripts pick up
    an exported override without importing pydantic settings.
    """
    override = os.environ.get(OFFICIAL_DB_ROOT_ENV)
    return Path(override).expanduser() if override else _DEFAULT_OFFICIAL_DB_ROOT


def schema_only_database_root() -> Path:
    """Return the schema-only placeholder benchmark database root.

    Honors ``T2S_BENCHMARK_SCHEMA_ONLY_ROOT`` when set, otherwise the in-repo
    default.
    """
    override = os.environ.get(SCHEMA_ONLY_DB_ROOT_ENV)
    return Path(override).expanduser() if override else _DEFAULT_SCHEMA_ONLY_DB_ROOT
