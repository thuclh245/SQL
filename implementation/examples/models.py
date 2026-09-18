from __future__ import annotations
from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, Field

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

class SolverOutput(BaseModel):
    sql: str
    dialect: Literal["postgres", "clickhouse", "starrocks", "sqlite"]
    expected_columns: list[str] = []
    assumptions: list[str] = []
    unresolved: list[str] = []

class Finding(BaseModel):
    code: str
    severity: Literal["info", "flag", "block"]
    message: str
    evidence_refs: list[str] = []

class DBObservation(BaseModel):
    action: Literal["explain", "dry_run", "probe", "execute"]
    success: bool
    elapsed_ms: int
    row_count: int | None = None
    scanned_bytes: int | None = None
    error_code: str | None = None
    error_message: str | None = None
    result_fingerprint: str | None = None

class Budget(BaseModel):
    max_rounds: int = 2
    max_solver_calls: int = 3
    max_schema_expansions: int = 2
    max_db_probes: int = 4
    max_repairs: int = 1
    max_verifier_calls: int = 1
