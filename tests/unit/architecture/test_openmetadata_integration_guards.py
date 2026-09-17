"""V2-P01 governance guards for the OpenMetadata integration path.

Verifies that the OpenMetadata code path preserves the Tier-1 invariants
required by V2-P01:

- read-only (§10): no HTTP write methods reachable from the MG0 assembly;
- boundary hygiene (§20): OpenMetadata client types do not leak into
  ``t2s.grounding`` / ``t2s.solver`` / ``t2s.runtime`` — the provider is the
  boundary;
- source-of-truth rule (§5): the OpenMetadata bytes fetched by the default
  client do not include ``sampleData`` / ``profile`` / ``queryHistory`` /
  ``lineage`` / ``columnStats`` in the fields query;
- fail-closed configuration (§22): metadata_provider='openmetadata' without a
  URL is rejected at factory construction;
- provider isolation (§21): StaticMetadataProvider is preserved.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from t2s.catalog.metadata_provider_factory import MetadataProviderFactory
from t2s.catalog.static_metadata_provider import StaticMetadataProvider
from t2s.configuration.settings import Settings
from t2s.errors.application_errors import ConfigurationError
from t2s.integrations.openmetadata.openmetadata_client import (
    DEFAULT_TABLE_FIELDS,
    OpenMetadataClient,
)

FORBIDDEN_OM_FIELDS = frozenset(
    {"sampleData", "profile", "queryHistory", "lineage", "columnStats", "customProperties"}
)

FORBIDDEN_WRITE_HTTP_METHODS = frozenset(
    {"post", "put", "patch", "delete", "head_write", "options_write"}
)

# HTTP client method names that would perform mutating requests if invoked with
# a live server. httpx's Client exposes these; the T2S client must never call
# any of them.
FORBIDDEN_HTTPX_CALLS = frozenset({"post", "put", "patch", "delete"})


def test_default_openmetadata_fields_exclude_sensitive_or_uncertified_data() -> None:
    """OpenMetadata's default fields query must not fetch data that MG0 is not certified to consume.

    V2-P01 §7 explicitly forbids sample rows, profile values, query history,
    lineage-derived joins, column statistics, and custom properties from
    becoming solver evidence in this phase.
    """
    default_fields = {field.strip() for field in DEFAULT_TABLE_FIELDS.split(",")}
    leaked = default_fields & FORBIDDEN_OM_FIELDS
    assert not leaked, (
        f"DEFAULT_TABLE_FIELDS contains fields V2-P01 forbids from MG0 solver evidence: {leaked}. "
        f"MG0 remains OFF for sampleData/profile/queryHistory/lineage/columnStats until each is "
        f"certified via the Doc 04 lifecycle."
    )


def test_openmetadata_client_source_uses_no_write_http_methods() -> None:
    """Static analysis of the OpenMetadata client: no httpx write calls.

    Walk the client module AST and confirm no ``.post`` / ``.put`` / ``.patch``
    / ``.delete`` attribute call is present. V2-P01 §10 requires the runtime
    OpenMetadata path to be read-only.
    """
    client_path = Path("src/t2s/integrations/openmetadata/openmetadata_client.py")
    source = client_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(client_path))

    violations: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr in FORBIDDEN_HTTPX_CALLS:
                violations.append((node.lineno, func.attr))

    assert not violations, (
        f"OpenMetadata client contains write-style HTTP method calls: {violations}. "
        "V2-P01 requires the runtime OpenMetadata path to be read-only."
    )


def test_openmetadata_client_does_not_expose_write_public_methods() -> None:
    """The public surface of :class:`OpenMetadataClient` is read-only."""
    public_methods = {
        name for name in dir(OpenMetadataClient) if not name.startswith("_")
    }
    write_prefixes = (
        "create_",
        "update_",
        "put_",
        "delete_",
        "patch_",
        "post_",
        "write_",
    )
    write_like = {
        name
        for name in public_methods
        if any(name.startswith(prefix) for prefix in write_prefixes)
    }
    assert not write_like, (
        f"OpenMetadataClient exposes write-style public methods: {write_like}. "
        "V2-P01 requires the runtime OpenMetadata path to be read-only."
    )


def test_grounding_and_solver_do_not_import_openmetadata_types() -> None:
    """MG0-facing packages must not import OpenMetadata SDK/client types.

    The provider is the only boundary that speaks OpenMetadata. If
    :mod:`t2s.grounding`, :mod:`t2s.solver`, or :mod:`t2s.runtime` imported
    :mod:`t2s.integrations.openmetadata`, the abstraction would be broken.
    """
    package_roots = [Path("src/t2s/grounding"), Path("src/t2s/solver"), Path("src/t2s/runtime")]
    violations: list[tuple[str, int, str]] = []
    for package_root in package_roots:
        for module_path in package_root.rglob("*.py"):
            if module_path.name.startswith("__"):
                # __init__ can be empty; still parse it.
                pass
            try:
                tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    module_name = node.module or ""
                    if module_name.startswith("t2s.integrations.openmetadata"):
                        violations.append((str(module_path), node.lineno, module_name))
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.startswith("t2s.integrations.openmetadata"):
                            violations.append((str(module_path), node.lineno, alias.name))
    assert not violations, (
        "MG0-facing packages import OpenMetadata integration types directly; the provider "
        f"must be the sole boundary. Violations: {violations}"
    )


def test_metadata_provider_factory_fails_closed_when_openmetadata_url_missing() -> None:
    """V2-P22 fail-closed rule: 'openmetadata' without URL raises ConfigurationError."""
    settings = Settings(metadata_provider="openmetadata", openmetadata_url=None)
    with pytest.raises(ConfigurationError, match="openmetadata_url is required"):
        MetadataProviderFactory.create_provider(settings)


def test_metadata_provider_factory_supports_only_known_providers() -> None:
    """Unsupported provider names must be rejected (no silent fallback)."""
    settings = Settings(metadata_provider="wren_cube_hybrid_v9")
    with pytest.raises(ConfigurationError, match="Unsupported metadata provider"):
        MetadataProviderFactory.create_provider(settings)


def test_static_metadata_provider_is_preserved_for_evaluation(tmp_path: Path) -> None:
    """V2-P21: StaticMetadataProvider remains usable independent of OpenMetadata.

    Benchmark evaluation must not become dependent on a live OpenMetadata server;
    the Static provider is the deterministic-fixture path.
    """
    import json

    catalog = [
        {
            "table_fqn": "warehouse.analytics.sales.customers",
            "service_name": "warehouse",
            "database_name": "analytics",
            "schema_name": "sales",
            "table_name": "customers",
            "columns": [
                {
                    "column_fqn": "warehouse.analytics.sales.customers.id",
                    "column_name": "id",
                    "data_type": "BIGINT",
                    "is_primary_key": True,
                    "ordinal_position": 1,
                }
            ],
            "primary_key_column_names": ["id"],
        }
    ]
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")

    provider = StaticMetadataProvider(catalog_tables_path=catalog_path)
    tables = provider.fetch_metadata()
    assert len(tables) == 1
    assert tables[0].table_fqn == "warehouse.analytics.sales.customers"
    assert provider.source_system == "static"


def test_canonical_catalog_table_has_no_sample_or_profile_fields() -> None:
    """Guard against a future edit that adds sample rows or profile stats to CatalogTable.

    V2-P01 §7 and §26: fetching or persisting sample/profile data in the
    canonical DTO would let MG0 accidentally consume uncertified evidence.
    """
    from t2s.catalog.canonical_metadata import CatalogColumn, CatalogTable

    forbidden_table_fields = {"sample_rows", "sample_data", "profile", "query_history", "lineage"}
    forbidden_column_fields = {"sample_values", "profile", "column_stats", "value_dictionary"}

    table_fields = set(CatalogTable.model_fields.keys())
    column_fields = set(CatalogColumn.model_fields.keys())

    table_leaks = table_fields & forbidden_table_fields
    column_leaks = column_fields & forbidden_column_fields

    assert not table_leaks, (
        f"CatalogTable exposes fields that V2-P01 forbids from MG0 evidence: {table_leaks}"
    )
    assert not column_leaks, (
        f"CatalogColumn exposes fields that V2-P01 forbids from MG0 evidence: {column_leaks}"
    )


def test_openmetadata_provider_marks_source_system_as_openmetadata() -> None:
    """Provider self-identifies as 'openmetadata' for audit trail (§27)."""
    from t2s.catalog.openmetadata_provider import OpenMetadataProvider

    client = OpenMetadataClient(base_url="http://openmetadata.test")
    provider = OpenMetadataProvider(client=client, pilot_fqns=["s.d.sc.t"])
    assert provider.source_system == "openmetadata"


def test_openmetadata_default_settings_do_not_activate_openmetadata_provider() -> None:
    """Repository default remains deterministic — OpenMetadata is opt-in (§23)."""
    settings = Settings()
    assert settings.metadata_provider is None, (
        "Repository default must not activate OpenMetadata; the LAB deployment profile "
        f"explicitly selects it. Current default: metadata_provider={settings.metadata_provider!r}"
    )
