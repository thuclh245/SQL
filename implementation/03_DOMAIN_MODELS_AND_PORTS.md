# 03 — Domain Models and Ports

## 1. Core request models

```python
class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    locale: Literal["vi", "en", "auto"] = "auto"
    target_hint: str | None = None
    client_request_id: str | None = None

class UserContext(BaseModel):
    subject: str
    groups: set[str] = set()
    roles: set[str] = set()
    claims_hash: str

class AuthorizedScope(BaseModel):
    scope_id: str
    allowed_services: set[str] = set()
    allowed_databases: set[str] = set()
    allowed_schemas: set[str] = set()
    allowed_table_fqns: set[str] | None = None
```

`UserContext` is built from trusted SSO/JWT middleware. The request body must never be allowed to choose a user identity.

## 2. Grounding contract

```python
class EvidenceRef(BaseModel):
    kind: Literal["metadata", "glossary", "profile", "query_history", "db_probe", "semantic"]
    source_id: str
    source_version: str | None = None
    observed_at: datetime | None = None
    summary: str

class TableContext(BaseModel):
    fqn: str
    description: str | None = None
    columns: list[ColumnContext]
    relationships: list[RelationshipEvidence] = []

class GroundingContext(BaseModel):
    scope_id: str
    tables: list[TableContext]
    glossary_hits: list[GlossaryHit] = []
    value_bindings: list[ValueBinding] = []
    unresolved: list[GroundingIssue] = []
    examples: list[ValidatedQueryExample] = []
    evidence: list[EvidenceRef] = []
    retrieval_signals: dict[str, float] = {}
```

Do not name local retrieval scores `confidence` unless they are actually calibrated. They are signals.

## 3. Solver contract

Use a **small operational envelope**, not a full mandatory IR:

```python
class SolverOutput(BaseModel):
    sql: str
    dialect: Literal["postgres", "clickhouse", "starrocks", "sqlite"]
    expected_columns: list[str] = []
    assumptions: list[str] = []
    unresolved: list[str] = []
```

This is intentionally not a semantic QueryPlan. It provides reliable machine parsing and operational metadata while preserving direct SQL as the mainline.

## 4. Verification models

```python
class Finding(BaseModel):
    code: str
    severity: Literal["info", "flag", "block"]
    message: str
    evidence_refs: list[str] = []

class VerificationReport(BaseModel):
    parsed: bool
    readonly: bool
    referenced_tables: set[str]
    referenced_columns: set[str]
    findings: list[Finding]
    canonical_sql: str | None = None
```

## 5. Database observation

```python
class DBObservation(BaseModel):
    action: Literal["explain", "dry_run", "probe", "execute"]
    success: bool
    elapsed_ms: int
    row_count: int | None = None
    scanned_bytes: int | None = None
    error_code: str | None = None
    error_message: str | None = None
    result_fingerprint: str | None = None
```

## 6. Orchestration state

```python
class Budget(BaseModel):
    max_rounds: int = 2
    max_solver_calls: int = 3
    max_schema_expansions: int = 2
    max_db_probes: int = 4
    max_verifier_calls: int = 1

class QueryState(BaseModel):
    trace_id: UUID
    request: QueryRequest
    user: UserContext
    scope: AuthorizedScope
    grounding: GroundingContext | None = None
    candidates: list[SQLCandidate] = []
    findings: list[Finding] = []
    db_observations: list[DBObservation] = []
    actions_taken: list[str] = []
    budget: Budget
```

Budget values are initial defaults only; tune them from shadow traffic.

## 7. Ports

```python
class AuthorizationPort(Protocol):
    async def resolve_scope(self, user: UserContext) -> AuthorizedScope: ...

class CatalogPort(Protocol):
    async def search(self, query: str, scope: AuthorizedScope, limit: int) -> list[AssetHit]: ...
    async def hydrate_tables(self, fqns: list[str]) -> list[TableContext]: ...
    async def lineage(self, fqn: str, depth: int = 1) -> LineageGraph: ...
    async def profiles(self, fqn: str) -> ProfileBundle | None: ...

class QueryLogPort(Protocol):
    async def search_validated_examples(self, query: str, scope: AuthorizedScope, limit: int) -> list[ValidatedQueryExample]: ...
    async def join_priors(self, table_fqns: list[str]) -> list[RelationshipEvidence]: ...

class LLMPort(Protocol):
    async def solve(self, req: SolverRequest) -> SolverOutput: ...
    async def verify_semantics(self, req: SemanticVerifyRequest) -> SemanticVerifyOutput: ...

class DatabaseGateway(Protocol):
    async def explain(self, ctx: DBRequestContext, sql: str) -> DBObservation: ...
    async def probe(self, ctx: DBRequestContext, probe: SafeProbe) -> DBObservation: ...
    async def execute(self, ctx: DBRequestContext, sql: str) -> QueryResult: ...
```
