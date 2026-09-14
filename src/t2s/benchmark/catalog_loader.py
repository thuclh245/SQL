import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from t2s.catalog import CatalogColumn, CatalogForeignKey, CatalogTable


def load_bird_catalog_tables(db_id: str, tables_json_path: Path) -> list[CatalogTable]:
    all_database_metadata = json.loads(tables_json_path.read_text(encoding="utf-8"))
    if not isinstance(all_database_metadata, list):
        raise ValueError(f"BIRD tables metadata must be a list: {tables_json_path}")

    db_entry = next(
        (
            database_metadata
            for database_metadata in all_database_metadata
            if database_metadata.get("db_id") == db_id
        ),
        None,
    )
    if db_entry is None:
        raise ValueError(f"Database '{db_id}' not found in {tables_json_path}")

    return _build_catalog_tables(db_id=db_id, db_entry=db_entry)


def _build_catalog_tables(db_id: str, db_entry: dict[str, Any]) -> list[CatalogTable]:
    table_names: list[str] = list(db_entry["table_names_original"])
    semantic_table_names: list[str] = list(db_entry.get("table_names", []))
    column_names: list[list[Any]] = list(db_entry["column_names_original"])
    semantic_column_names: list[list[Any]] = list(db_entry.get("column_names", []))
    column_types: list[str] = list(db_entry["column_types"])
    primary_keys = db_entry.get("primary_keys", [])
    foreign_keys = db_entry.get("foreign_keys", [])

    primary_key_column_indexes: set[int] = set()
    for primary_key in primary_keys:
        if isinstance(primary_key, int):
            primary_key_column_indexes.add(primary_key)
        elif isinstance(primary_key, list):
            primary_key_column_indexes.update(int(column_index) for column_index in primary_key)

    table_columns: dict[int, list[CatalogColumn]] = {
        table_index: [] for table_index in range(len(table_names))
    }
    column_index_to_table_column: dict[int, tuple[int, str]] = {}

    for column_index, (table_index, column_name) in enumerate(column_names):
        if table_index == -1:
            continue
        typed_table_index = int(table_index)
        data_type = column_types[column_index] if column_index < len(column_types) else "text"
        table_name = table_names[typed_table_index]
        semantic_column_name = (
            str(semantic_column_names[column_index][1])
            if column_index < len(semantic_column_names)
            and isinstance(semantic_column_names[column_index], list)
            and len(semantic_column_names[column_index]) == 2
            else None
        )
        catalog_column = CatalogColumn(
            column_fqn=f"{db_id}.main.{table_name}.{column_name}",
            column_name=str(column_name),
            data_type=str(data_type),
            description=_semantic_description(str(column_name), semantic_column_name),
            is_primary_key=column_index in primary_key_column_indexes,
            ordinal_position=len(table_columns[typed_table_index]) + 1,
        )
        table_columns[typed_table_index].append(catalog_column)
        column_index_to_table_column[column_index] = (typed_table_index, str(column_name))

    table_foreign_keys: dict[int, list[CatalogForeignKey]] = defaultdict(list)
    for foreign_key in foreign_keys:
        if not isinstance(foreign_key, list) or len(foreign_key) != 2:
            continue
        from_info = column_index_to_table_column.get(int(foreign_key[0]))
        to_info = column_index_to_table_column.get(int(foreign_key[1]))
        if from_info is None or to_info is None:
            continue
        from_table_index, from_column_name = from_info
        to_table_index, to_column_name = to_info
        from_table_name = table_names[from_table_index]
        to_table_name = table_names[to_table_index]
        table_foreign_keys[from_table_index].append(
            CatalogForeignKey(
                from_table_fqn=f"{db_id}.main.{from_table_name}",
                from_column_names=[from_column_name],
                to_table_fqn=f"{db_id}.main.{to_table_name}",
                to_column_names=[to_column_name],
                provenance="declared_foreign_key",
            )
        )

    catalog_tables: list[CatalogTable] = []
    for table_index, table_name in enumerate(table_names):
        semantic_table_name = (
            str(semantic_table_names[table_index])
            if table_index < len(semantic_table_names)
            else None
        )
        primary_key_names = [
            column.column_name for column in table_columns[table_index] if column.is_primary_key
        ]
        catalog_tables.append(
            CatalogTable(
                table_fqn=f"{db_id}.main.{table_name}",
                service_name=db_id,
                database_name=db_id,
                schema_name="main",
                table_name=table_name,
                description=_semantic_description(table_name, semantic_table_name),
                sql_identifier=table_name,
                sql_identifier_source="explicit",
                columns=table_columns[table_index],
                primary_key_column_names=primary_key_names,
                foreign_keys=table_foreign_keys.get(table_index, []),
            )
        )
    return catalog_tables


def _semantic_description(
    physical_name: str,
    semantic_name: str | None,
) -> str | None:
    if semantic_name is None:
        return None
    stripped_semantic_name = semantic_name.strip()
    if not stripped_semantic_name:
        return None
    if _normalize_description_text(physical_name) == _normalize_description_text(
        stripped_semantic_name
    ):
        return None
    return stripped_semantic_name


def _normalize_description_text(value: str) -> str:
    return value.strip().lower()
