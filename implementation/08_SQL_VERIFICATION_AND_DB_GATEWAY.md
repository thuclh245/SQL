# 08 — SQL Verification and Database Gateway

## 1. Verification pipeline

```text
SolverOutput.sql
 -> parse with explicit SQLGlot dialect
 -> single-statement/read-query policy
 -> extract referenced tables/columns
 -> authorization recheck
 -> dialect-specific static policy
 -> EXPLAIN/dry-run
 -> optional safe execution
```

SQLGlot officially supports ClickHouse, Postgres and StarRocks but is not a complete validator, so DB preflight remains mandatory. [R13–R14]

## 2. AST guard

Implementation outline:

```python
expr = sqlglot.parse_one(sql, dialect=dialect)
assert is_allowed_query_expression(expr)
assert not contains_write_or_admin_nodes(expr)
assert not contains_select_into(expr)
refs = collect_table_refs(expr)
authorizer.assert_allowed(scope, refs)
assert not contains_dangerous_functions(expr, dialect_policy)
canonical = expr.sql(dialect=dialect, pretty=False)
```

Use a test corpus for each dialect. Do not trust generic node names without verifying SQLGlot behavior/version.

## 3. DatabaseGateway contract

The gateway owns:

- connection selection and role mapping;
- transaction/session read-only enforcement;
- statement timeout;
- result row/byte caps;
- query tag / request trace ID;
- EXPLAIN/dry-run/probe/execute;
- audit and metrics;
- safe parameter binding for probes.

The orchestrator must never call a raw driver directly.

## 4. PostgreSQL adapter

For execution:

```sql
BEGIN READ ONLY;
SET LOCAL statement_timeout = '30s';
-- execute approved SELECT
COMMIT;
```

Use engine-appropriate pool settings and the effective read-only role. PostgreSQL documents read-only transaction mode and statement timeout. [R15–R16]

For preflight use `EXPLAIN` without `ANALYZE` by default. `EXPLAIN ANALYZE` executes the query and must not be treated as a cheap static check.

## 5. StarRocks adapter

- connect with a dedicated SELECT-only role/user;
- use `EXPLAIN` for plan validation; StarRocks documents LOGICAL/VERBOSE/COSTS modes [R21];
- use resource groups/warehouse limits according to company configuration;
- because StarRocks uses MySQL protocol, keep connection details inside the adapter [R19].

## 6. ClickHouse adapter

Use `clickhouse-connect` through a dedicated restricted account. Pass per-query settings for execution/time/result limits according to the installed ClickHouse version. [R17–R18]

Use ClickHouse `EXPLAIN` variants for preflight; do not use execution/analyze modes as a substitute for cheap validation unless explicitly budgeted.

## 7. SafeProbe API

Do not let the model send arbitrary probe SQL. Define typed probes:

```python
class ValueExistsProbe(BaseModel):
    table_fqn: str
    column: str
    value: str | int | float | date

class DistinctValuesProbe(BaseModel):
    table_fqn: str
    column: str
    limit: int = Field(le=20)
```

Gateway compiles these templates itself with parameter binding. Probe allow-list should exclude sensitive/high-cardinality columns unless policy permits.

## 8. Result handling

Return:

- column names/types;
- bounded rows;
- row count if cheaply known;
- query/plan diagnostics;
- result fingerprint for internal comparison.

Never normalize away semantically meaningful row ordering for user output. Result fingerprints used for candidate comparison are internal and must distinguish ordered top-k queries from unordered result sets.

## 9. Execution policy

v1 safest policy:

1. AST + auth pass;
2. EXPLAIN/dry-run pass;
3. risk policy permits execution;
4. execute selected SQL once;
5. if execution itself produces new diagnostic failure, at most one targeted recovery round according to budget.
