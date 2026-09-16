"""Metamorphic checks that value grounding carries no identifier knowledge.

Renaming a table and column while preserving data and metadata must not change
which literals are found. If any rule were keyed to a particular schema name,
these tests would diverge from their originals.
"""

import sqlite3
from pathlib import Path

from t2s.catalog import CatalogColumn, CatalogTable
from t2s.grounding.value_grounding import (
    SqliteValueProbe,
    ValueGrounder,
    ValueGroundingBudget,
)

QUESTION = "How many enterprise accounts are in the Northern region?"


def _build_database(directory: Path, table_name: str, column_name: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    database_path = directory / f"{table_name}.sqlite"
    connection = sqlite3.connect(database_path)
    connection.execute(
        f'CREATE TABLE "{table_name}" (row_key INTEGER PRIMARY KEY, "{column_name}" TEXT)'  # noqa: S608
    )
    connection.executemany(
        f'INSERT INTO "{table_name}" VALUES (?, ?)',  # noqa: S608
        [(1, "enterprise"), (2, "small_business"), (3, "consumer")],
    )
    connection.commit()
    connection.close()
    return database_path


def _build_catalog(table_name: str, column_name: str, description: str) -> list[CatalogTable]:
    return [
        CatalogTable(
            table_fqn=f"svc.db.main.{table_name}",
            service_name="svc",
            database_name="db",
            schema_name="main",
            table_name=table_name,
            sql_identifier=table_name,
            columns=[
                CatalogColumn(
                    column_fqn=f"svc.db.main.{table_name}.row_key",
                    column_name="row_key",
                    data_type="integer",
                    is_primary_key=True,
                ),
                CatalogColumn(
                    column_fqn=f"svc.db.main.{table_name}.{column_name}",
                    column_name=column_name,
                    data_type="text",
                    # Business meaning travels in the description, which is what
                    # relevance scoring is allowed to read.
                    description=description,
                ),
            ],
            primary_key_column_names=["row_key"],
        )
    ]


def _ground(database_path: Path, catalog_tables: list[CatalogTable]) -> list[str]:
    grounder = ValueGrounder(
        value_probe=SqliteValueProbe(database_path),
        budget=ValueGroundingBudget(),
    )
    result = grounder.ground_values(
        question=QUESTION,
        catalog_tables=catalog_tables,
        selected_column_names_by_table_fqn={
            table.table_fqn: {column.column_name for column in table.columns}
            for table in catalog_tables
        },
    )
    return sorted(binding.candidate_value for binding in result.bindings)


def test_renaming_table_and_column_preserves_bindings(tmp_path: Path) -> None:
    descriptive_path = _build_database(tmp_path / "a", "accounts", "tier")
    opaque_path = _build_database(tmp_path / "b", "alpha", "attr_x")

    descriptive_values = _ground(
        descriptive_path,
        _build_catalog("accounts", "tier", "Account tier"),
    )
    opaque_values = _ground(
        opaque_path,
        _build_catalog("alpha", "attr_x", "Account tier"),
    )

    assert descriptive_values == ["enterprise"]
    assert opaque_values == descriptive_values


def test_bindings_are_found_even_without_any_descriptive_metadata(tmp_path: Path) -> None:
    """Relevance ranking may prefer descriptive columns, but must not gate matching."""
    opaque_path = _build_database(tmp_path / "c", "alpha", "attr_x")

    values = _ground(opaque_path, _build_catalog("alpha", "attr_x", ""))

    assert values == ["enterprise"]
