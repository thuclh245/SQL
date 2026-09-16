"""PostgreSQL Metadata Provider.

Performs read-only schema introspection over PostgreSQL system catalogs,
assembling canonical `CatalogTable` models with strictly bounded queries (N=4),
preserving composite constraints, native types, descriptions, and tri-state nullability.
"""

from collections import defaultdict
from collections.abc import Callable
from typing import Any

from t2s.catalog.canonical_metadata import (
    AssetIdentity,
    AssetType,
    CatalogColumn,
    CatalogForeignKey,
    CatalogTable,
    MetadataProvenance,
)
from t2s.catalog.metadata_provider import MetadataProviderPort
from t2s.catalog.metadata_scope import MetadataScope
from t2s.errors.application_errors import (
    ConfigurationError,
    MetadataCatalogError,
    MetadataMappingError,
)

PostgresConnectionFactory = Callable[[], Any]

# System schemas excluded by default from business metadata acquisition
DEFAULT_SYSTEM_SCHEMAS: frozenset[str] = frozenset(
    {
        "pg_catalog",
        "information_schema",
        "pg_toast",
    }
)


def normalize_postgres_data_type(native_type: str, base_type: str) -> str:
    """Normalize PostgreSQL data types to general canonical representations.

    Guarantees that unknown or extension types do not abort ingestion, while
    known types map cleanly to general SQL categories.
    """
    clean_native = native_type.strip().lower()
    clean_base = base_type.strip().lower()

    if clean_native.endswith("[]") or clean_base.startswith("_"):
        return "ARRAY"

    if clean_base in {"int2", "smallint", "smallserial"}:
        return "SMALLINT"
    if clean_base in {"int4", "integer", "serial"}:
        return "INTEGER"
    if clean_base in {"int8", "bigint", "bigserial"}:
        return "BIGINT"
    if clean_base in {"bool", "boolean"}:
        return "BOOLEAN"
    if clean_base in {"float4", "real"}:
        return "FLOAT"
    if clean_base in {"float8", "double precision"}:
        return "DOUBLE"
    if clean_base in {"numeric", "decimal"}:
        return "DECIMAL"
    if clean_base in {"varchar", "character varying"}:
        return "VARCHAR"
    if clean_base in {"char", "bpchar", "character"}:
        return "CHAR"
    if clean_base in {"text", "citext"}:
        return "TEXT"
    if clean_base == "date":
        return "DATE"
    if "timestamp" in clean_base or "timestamp" in clean_native:
        return "TIMESTAMP"
    if clean_base in {"time", "timetz"} or "time " in clean_native:
        return "TIME"
    if clean_base == "interval":
        return "INTERVAL"
    if clean_base == "json":
        return "JSON"
    if clean_base == "jsonb":
        return "JSONB"
    if clean_base == "bytea":
        return "BLOB"
    if clean_base == "uuid":
        return "UUID"

    # Fallback to uppercase base type for custom / extension types
    cleaned = clean_base.split("(")[0].strip().upper()
    return cleaned if cleaned else "OTHER"


def _build_pushdown_conditions(
    scope: MetadataScope | None,
    schema_col: str = "n.nspname",
    table_col: str = "c.relname",
) -> tuple[str, list[Any]]:
    """Build parameterized WHERE clauses for source-side scope pushdown."""
    if scope is None:
        return "", []

    clauses: list[str] = []
    params: list[Any] = []

    if scope.schema_names is not None:
        exact_schemas = [
            s for s in scope.schema_names if not any(c in s for c in ("*", "?", "[", "]"))
        ]
        if exact_schemas:
            clauses.append(f"AND {schema_col} = ANY(%s)")
            params.append(sorted(exact_schemas))

    if scope.exclude_schemas is not None:
        exact_exclude = [
            s for s in scope.exclude_schemas if not any(c in s for c in ("*", "?", "[", "]"))
        ]
        if exact_exclude:
            clauses.append(f"AND {schema_col} != ALL(%s)")
            params.append(sorted(exact_exclude))

    if scope.include_tables is not None:
        exact_tables = set()
        for pat in scope.include_tables:
            if not any(c in pat for c in ("*", "?", "[", "]")):
                t_name = pat.split(".")[-1] if "." in pat else pat
                exact_tables.add(t_name)
        if exact_tables:
            clauses.append(f"AND {table_col} = ANY(%s)")
            params.append(sorted(exact_tables))

    return " ".join(clauses), params


class PostgresMetadataProvider(MetadataProviderPort):
    """Acquires canonical metadata directly from PostgreSQL system catalogs.

    Architecture Invariants:
    1. Bounded queries: exactly 4 bulk SQL queries per fetch, regardless of table count.
    2. Linear assembly: O(metadata records) dictionary index joins.
    3. Read-only session: enforces SET TRANSACTION READ ONLY with statement timeout.
    4. Structural fidelity: composite PKs, composite FKs, and cross-schema FKs preserved.
    5. Clean provenance: source_system='postgresql', source_entity_id='<schema>.<table>'.
    """

    # Query 1: Assets (tables, views, materialized views, partitioned tables) + descriptions
    SQL_RELATIONS = """
    SELECT
        current_database() AS database_name,
        n.nspname AS schema_name,
        c.relname AS table_name,
        c.relkind AS relkind,
        d.description AS table_description
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    LEFT JOIN pg_description d ON d.objoid = c.oid AND d.objsubid = 0
    WHERE c.relkind IN ('r', 'v', 'm', 'p')
      AND n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
      AND n.nspname NOT LIKE 'pg_temp_%'
      AND n.nspname NOT LIKE 'pg_toast_temp_%'
    ORDER BY n.nspname, c.relname;
    """

    # Query 2: Columns + native type + ordinal position + nullability + descriptions
    SQL_COLUMNS = """
    SELECT
        n.nspname AS schema_name,
        c.relname AS table_name,
        a.attname AS column_name,
        a.attnum AS ordinal_position,
        format_type(a.atttypid, a.atttypmod) AS native_type,
        t.typname AS base_type,
        NOT a.attnotnull AS is_nullable,
        d.description AS column_description
    FROM pg_attribute a
    JOIN pg_class c ON c.oid = a.attrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    JOIN pg_type t ON t.oid = a.atttypid
    LEFT JOIN pg_description d ON d.objoid = c.oid AND d.objsubid = a.attnum
    WHERE a.attnum > 0
      AND NOT a.attisdropped
      AND c.relkind IN ('r', 'v', 'm', 'p')
      AND n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
      AND n.nspname NOT LIKE 'pg_temp_%'
      AND n.nspname NOT LIKE 'pg_toast_temp_%'
    ORDER BY n.nspname, c.relname, a.attnum;
    """

    # Query 3: Primary Keys (single & composite) with declared key ordinal
    SQL_PRIMARY_KEYS = """
    SELECT
        n.nspname AS schema_name,
        c.relname AS table_name,
        con.conname AS constraint_name,
        a.attname AS column_name,
        k.ord AS key_ordinal
    FROM pg_constraint con
    JOIN pg_class c ON c.oid = con.conrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    CROSS JOIN LATERAL unnest(con.conkey) WITH ORDINALITY AS k(attnum, ord)
    JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = k.attnum
    WHERE con.contype = 'p'
      AND c.relkind IN ('r', 'p')
      AND n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
      AND n.nspname NOT LIKE 'pg_temp_%'
      AND n.nspname NOT LIKE 'pg_toast_temp_%'
    ORDER BY n.nspname, c.relname, k.ord;
    """

    # Query 4: Foreign Keys (single, composite, cross-schema) with paired column ordinals
    SQL_FOREIGN_KEYS = """
    SELECT
        con.conname AS constraint_name,
        src_n.nspname AS from_schema,
        src_c.relname AS from_table,
        src_a.attname AS from_column,
        dst_n.nspname AS to_schema,
        dst_c.relname AS to_table,
        dst_a.attname AS to_column,
        k.ord AS key_ordinal
    FROM pg_constraint con
    JOIN pg_class src_c ON src_c.oid = con.conrelid
    JOIN pg_namespace src_n ON src_n.oid = src_c.relnamespace
    JOIN pg_class dst_c ON dst_c.oid = con.confrelid
    JOIN pg_namespace dst_n ON dst_n.oid = dst_c.relnamespace
    CROSS JOIN LATERAL unnest(con.conkey, con.confkey)
        WITH ORDINALITY AS k(src_attnum, dst_attnum, ord)
    JOIN pg_attribute src_a ON src_a.attrelid = src_c.oid AND src_a.attnum = k.src_attnum
    JOIN pg_attribute dst_a ON dst_a.attrelid = dst_c.oid AND dst_a.attnum = k.dst_attnum
    WHERE con.contype = 'f'
      AND src_n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
      AND src_n.nspname NOT LIKE 'pg_temp_%'
      AND src_n.nspname NOT LIKE 'pg_toast_temp_%'
    ORDER BY src_n.nspname, src_c.relname, con.conname, k.ord;
    """

    def __init__(
        self,
        database_url: str | None = None,
        service_name: str = "postgresql",
        database_name: str | None = None,
        connect_timeout_seconds: int = 10,
        statement_timeout_seconds: int = 30,
        connection_factory: PostgresConnectionFactory | None = None,
    ) -> None:
        if connection_factory is None and not database_url:
            raise ConfigurationError(
                "PostgresMetadataProvider requires either 'database_url' or 'connection_factory'."
            )
        self.database_url = database_url
        self.service_name = service_name.strip()
        self._database_name = database_name.strip() if database_name else None
        self.connect_timeout_seconds = connect_timeout_seconds
        self.statement_timeout_seconds = statement_timeout_seconds
        self.connection_factory = connection_factory or self._connect

    @property
    def source_system(self) -> str:
        return "postgresql"

    def fetch_metadata(self, scope: MetadataScope | None = None) -> list[CatalogTable]:
        """Fetch, scope, normalize, and validate canonical table metadata from PostgreSQL."""
        try:
            raw_relations, raw_columns, raw_pks, raw_fks = self._execute_bulk_metadata_queries(
                scope
            )
        except MetadataCatalogError:
            raise
        except Exception as exc:
            raise MetadataCatalogError(
                f"PostgreSQL metadata query execution failed: {exc}"
            ) from exc

        return self._assemble_canonical_tables(
            raw_relations=raw_relations,
            raw_columns=raw_columns,
            raw_pks=raw_pks,
            raw_fks=raw_fks,
            scope=scope,
        )

    def _connect(self) -> Any:
        import psycopg

        assert self.database_url is not None
        return psycopg.connect(
            self.database_url,
            autocommit=False,
            connect_timeout=self.connect_timeout_seconds,
        )

    @staticmethod
    def _inject_conditions(query: str, conditions: str) -> str:
        if not conditions:
            return query
        parts = query.split("ORDER BY")
        return f"{parts[0]} {conditions} ORDER BY{parts[1]}"

    def _execute_bulk_metadata_queries(
        self,
        scope: MetadataScope | None = None,
    ) -> tuple[
        list[tuple[Any, ...]],
        list[tuple[Any, ...]],
        list[tuple[Any, ...]],
        list[tuple[Any, ...]],
    ]:
        """Execute the 4 bounded bulk SQL metadata queries with source-side scope pushdown."""
        connection = self.connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute("SET TRANSACTION READ ONLY")
            cursor.execute(f"SET LOCAL statement_timeout = {self.statement_timeout_seconds * 1000}")

            cond_std, params_std = _build_pushdown_conditions(scope, "n.nspname", "c.relname")
            cond_fk, params_fk = _build_pushdown_conditions(scope, "src_n.nspname", "src_c.relname")

            sql_rel = self._inject_conditions(self.SQL_RELATIONS, cond_std)
            cursor.execute(sql_rel, params_std if params_std else None)
            relations = list(cursor.fetchall())

            sql_cols = self._inject_conditions(self.SQL_COLUMNS, cond_std)
            cursor.execute(sql_cols, params_std if params_std else None)
            columns = list(cursor.fetchall())

            sql_pks = self._inject_conditions(self.SQL_PRIMARY_KEYS, cond_std)
            cursor.execute(sql_pks, params_std if params_std else None)
            pks = list(cursor.fetchall())

            sql_fks = self._inject_conditions(self.SQL_FOREIGN_KEYS, cond_fk)
            cursor.execute(sql_fks, params_fk if params_fk else None)
            fks = list(cursor.fetchall())

            return relations, columns, pks, fks
        except Exception as exc:
            raise MetadataCatalogError(f"PostgreSQL metadata fetch failed: {exc}") from exc
        finally:
            try:
                connection.rollback()
            except Exception:
                pass
            try:
                connection.close()
            except Exception:
                pass

    def _assemble_canonical_tables(
        self,
        raw_relations: list[tuple[Any, ...]],
        raw_columns: list[tuple[Any, ...]],
        raw_pks: list[tuple[Any, ...]],
        raw_fks: list[tuple[Any, ...]],
        scope: MetadataScope | None,
    ) -> list[CatalogTable]:
        # Index 1: Primary keys by (schema, table) -> ordered list of pk column names
        pk_columns_by_table: dict[tuple[str, str], list[tuple[int, str]]] = defaultdict(list)
        for row in raw_pks:
            schema_name, table_name, _, col_name, key_ord = row
            pk_columns_by_table[(schema_name, table_name)].append((int(key_ord), col_name))

        sorted_pks_by_table: dict[tuple[str, str], list[str]] = {}
        for key, pks in pk_columns_by_table.items():
            pks.sort(key=lambda item: item[0])
            sorted_pks_by_table[key] = [col_name for _, col_name in pks]

        # Index 2: Foreign keys by (from_schema, from_table, constraint_name)
        fks_grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
        for row in raw_fks:
            con_name, from_schema, from_table, from_col, to_schema, to_table, to_col, key_ord = row
            fk_key = (from_schema, from_table, con_name)
            if fk_key not in fks_grouped:
                fks_grouped[fk_key] = {
                    "from_schema": from_schema,
                    "from_table": from_table,
                    "to_schema": to_schema,
                    "to_table": to_table,
                    "pairs": [],
                }
            fks_grouped[fk_key]["pairs"].append((int(key_ord), from_col, to_col))

        fks_by_table: dict[tuple[str, str], list[CatalogForeignKey]] = defaultdict(list)
        for (from_schema, from_table, con_name), fk_data in fks_grouped.items():
            fk_data["pairs"].sort(key=lambda p: p[0])
            from_cols = [p[1] for p in fk_data["pairs"]]
            to_cols = [p[2] for p in fk_data["pairs"]]
            db = self._database_name or "postgres"
            from_fqn = AssetIdentity.build_canonical_fqn(
                self.service_name, db, from_schema, from_table
            )
            to_fqn = AssetIdentity.build_canonical_fqn(
                self.service_name, db, fk_data["to_schema"], fk_data["to_table"]
            )
            catalog_fk = CatalogForeignKey(
                relationship_name=con_name,
                from_table_fqn=from_fqn,
                from_column_names=from_cols,
                to_table_fqn=to_fqn,
                to_column_names=to_cols,
                provenance="declared_foreign_key",
            )
            fks_by_table[(from_schema, from_table)].append(catalog_fk)

        # Index 3: Columns by (schema, table)
        columns_by_table: dict[tuple[str, str], list[CatalogColumn]] = defaultdict(list)
        for row in raw_columns:
            schema_name, table_name, col_name, attnum, native_type, base_type, is_null, desc = row
            db = self._database_name or "postgres"
            table_fqn = AssetIdentity.build_canonical_fqn(
                self.service_name, db, schema_name, table_name
            )
            col_fqn = f"{table_fqn}.{col_name}"
            data_type = normalize_postgres_data_type(str(native_type), str(base_type))
            table_pk_cols = set(sorted_pks_by_table.get((schema_name, table_name), []))

            col = CatalogColumn(
                column_fqn=col_fqn,
                column_name=str(col_name),
                data_type=data_type,
                native_type=str(native_type),
                description=str(desc) if desc else None,
                is_nullable=bool(is_null) if is_null is not None else None,
                is_primary_key=col_name in table_pk_cols,
                ordinal_position=int(attnum) if attnum is not None else None,
            )
            columns_by_table[(schema_name, table_name)].append(col)

        # Index 4: Assemble CatalogTables
        catalog_tables: list[CatalogTable] = []
        for row in raw_relations:
            db_name_from_query, schema_name, table_name, relkind, table_desc = row
            resolved_db = self._database_name or str(db_name_from_query)

            asset_type: AssetType = "table"
            if relkind == "v":
                asset_type = "view"
            elif relkind == "m":
                asset_type = "materialized_view"

            # Apply Controlled Metadata Scope
            if scope is not None:
                if not scope.matches_table(
                    table_name=table_name,
                    schema_name=schema_name,
                    database_name=resolved_db,
                    asset_type=asset_type,
                ):
                    continue

            table_key = (schema_name, table_name)
            table_cols = sorted(
                columns_by_table.get(table_key, []),
                key=lambda c: c.ordinal_position or 999999,
            )
            table_pks = sorted_pks_by_table.get(table_key, [])
            table_fks = fks_by_table.get(table_key, [])

            asset_id = AssetIdentity.from_parts(
                service_name=self.service_name,
                database_name=resolved_db,
                schema_name=schema_name,
                asset_name=table_name,
                asset_type=asset_type,
            )

            try:
                catalog_table = CatalogTable(
                    table_fqn=asset_id.canonical_fqn,
                    service_name=self.service_name,
                    database_name=resolved_db,
                    schema_name=schema_name,
                    table_name=table_name,
                    table_type=asset_type,
                    description=str(table_desc) if table_desc else None,
                    sql_identifier=table_name,
                    sql_identifier_source="explicit",
                    columns=table_cols,
                    primary_key_column_names=table_pks,
                    foreign_keys=table_fks,
                    provenance=MetadataProvenance(
                        source_system="postgresql",
                        source_entity_id=f"{schema_name}.{table_name}",
                    ),
                )
                catalog_tables.append(catalog_table)
            except Exception as exc:
                raise MetadataMappingError(
                    f"PostgreSQL metadata validation failed for '{asset_id.canonical_fqn}': {exc}"
                ) from exc

        # Deterministic sorting by canonical FQN
        return sorted(catalog_tables, key=lambda t: t.table_fqn)
