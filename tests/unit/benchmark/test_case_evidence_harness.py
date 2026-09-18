"""E04 case-evidence harness tests (§20).

These use synthetic, generic fixtures only — no benchmark question or gold text
enters any test — and never call a live LLM. A deterministic fake chat client and
a temporary SQLite database drive the real runtime pipeline so the captured
evidence reflects real behavior.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from t2s.benchmark.case_evidence import (
    CaseEvidenceRecorder,
    EvidenceCompleteness,
    GenerationOutcome,
    RecordingChatClient,
    all_hashes_valid,
    classify_evidence_completeness,
    load_case_record,
    recording_schema_serializer,
    reset_active_case,
    set_active_case,
    sha256_json,
    sha256_text,
    verify_record_hashes,
    write_case_record,
)
from t2s.benchmark.case_evidence.emit import EvidenceEmitter, grounding_config_hash
from t2s.benchmark.scoring import compute_result_fingerprint
from t2s.catalog import (
    CatalogColumn,
    CatalogSearchDocumentBuilder,
    CatalogTable,
)
from t2s.catalog.in_memory_catalog import InMemoryCatalog
from t2s.database import QueryExecutionPolicy
from t2s.database.sqlite_read_only_query_executor import SqliteReadOnlyQueryExecutor
from t2s.grounding import GroundingContextBuilder, SchemaRetriever
from t2s.grounding.schema_retriever import InMemorySchemaSearch
from t2s.runtime import RuntimeStatus, TextToSqlRuntime
from t2s.runtime.runtime_assembly import assemble_semantic_runtime
from t2s.runtime.runtime_profile import SemanticRuntimeProfile
from t2s.security import AuthorizationService, AuthorizedSqlResource, UserIdentity
from t2s.solver.solver_response import StructuredChatResponse

PROMPT_DIR = Path("prompts/direct_sql")
CANDIDATE_SQL = "SELECT name FROM customers"


class _AllowCustomers:
    def get_authorized_resources(self, user_identity: UserIdentity) -> list[AuthorizedSqlResource]:
        return [
            AuthorizedSqlResource(catalog_fqn="db.main.customers", sql_identifier="customers")
        ]


class _FakeChatClient:
    """Deterministic provider. Behavior chosen by the active case scope key."""

    def __init__(self, behavior: dict[str, str] | None = None) -> None:
        self.behavior = behavior or {}
        self.calls: list[dict[str, str]] = []
        self.seen_messages: list[list[dict[str, str]]] = []

    async def generate_structured_response(
        self,
        messages: list[dict[str, str]],
        response_schema: dict[str, Any],
        model_name: str,
        reasoning_effort: str | None,
        max_output_tokens: int,
    ) -> StructuredChatResponse:
        self.calls.append({"model": model_name})
        self.seen_messages.append([dict(m) for m in messages])
        from t2s.benchmark.case_evidence import active_case_key
        from t2s.errors import SolverDependencyError

        mode = self.behavior.get(active_case_key() or "", "ok")
        if mode == "provider_error":
            raise SolverDependencyError("injected provider error")
        sql = "" if mode == "empty" else CANDIDATE_SQL
        return StructuredChatResponse(
            content={
                "sql": sql,
                "dialect": "sqlite",
                "referenced_tables": ["customers"],
                "referenced_columns": ["customers.name"],
                "expected_columns": ["name"],
                "assumptions": [],
                "unresolved": [],
            },
            model_name=model_name,
            elapsed_ms=3,
            prompt_tokens=5,
            output_tokens=2,
        )


def _make_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "fixture.sqlite"
    connection = sqlite3.connect(db_path)
    connection.execute("CREATE TABLE customers (name TEXT)")
    connection.executemany(
        "INSERT INTO customers (name) VALUES (?)", [("Ada",), ("Grace",), ("Ada",)]
    )
    connection.commit()
    connection.close()
    return db_path


def _build_runtime(
    tmp_path: Path,
    recorder: CaseEvidenceRecorder,
    behavior: dict[str, str] | None = None,
) -> tuple[TextToSqlRuntime, Path, _FakeChatClient]:
    fake = _FakeChatClient(behavior)
    chat_client = RecordingChatClient(fake, recorder)
    db_path = _make_db(tmp_path)
    table = CatalogTable(
        table_fqn="db.main.customers",
        service_name="sqlite",
        database_name="db",
        schema_name="main",
        table_name="customers",
        sql_identifier="customers",
        sql_identifier_source="explicit",
        columns=[
            CatalogColumn(
                column_fqn="db.main.customers.name", column_name="name", data_type="TEXT"
            )
        ],
    )
    catalog = InMemoryCatalog()
    catalog.upsert_tables([table])
    documents = CatalogSearchDocumentBuilder().build_search_documents(table)
    grounding_builder = GroundingContextBuilder(
        catalog=catalog,
        schema_retriever=SchemaRetriever(InMemorySchemaSearch(documents)),
        authorization_service=AuthorizationService(_AllowCustomers()),
    )
    runtime = assemble_semantic_runtime(
        grounding_context_builder=grounding_builder,
        authorization_service=AuthorizationService(_AllowCustomers()),
        query_executor=SqliteReadOnlyQueryExecutor(db_path),
        chat_client=chat_client,
        prompt_directory=PROMPT_DIR,
        execution_policy=QueryExecutionPolicy(
            maximum_result_rows=100, statement_timeout_seconds=10
        ),
        default_dialect="sqlite",
        profile=SemanticRuntimeProfile(model_name="fake-model", temperature=0.0),
        schema_serializer=recording_schema_serializer(recorder),
    )
    return runtime, db_path, fake


async def _run_one(
    runtime: TextToSqlRuntime,
    question: str,
    case_run_id: str,
) -> Any:
    from t2s.contracts import QueryRequest

    token = set_active_case(case_run_id)
    try:
        return await runtime.execute_query_pipeline(
            query_request=QueryRequest(question=question, database_dialect="sqlite"),
            user_identity=UserIdentity(user_id="test", tenant_id="t2s"),
            run_id=case_run_id,
        )
    finally:
        reset_active_case(token)


def _emitter(tmp_path: Path, recorder: CaseEvidenceRecorder, **overrides: Any) -> EvidenceEmitter:
    profile = SemanticRuntimeProfile(model_name="fake-model", temperature=0.0)
    defaults: dict[str, Any] = dict(
        evidence_root=tmp_path / "evidence",
        experiment_id="exp1",
        run_id="run1",
        replicate_id="r01",
        recorder=recorder,
        profile=profile,
        provider="fake",
        dataset_name="synthetic.jsonl",
        dataset_split="dev",
        dataset_version_or_hash="deadbeef",
        source_commit="c0ffee",
        source_dirty=False,
        grounding_strategy="adaptive_orchestrator",
        grounding_config_hash=grounding_config_hash(profile),
    )
    defaults.update(overrides)
    return EvidenceEmitter(**defaults)


# 0. instrumentation is observational: identical runtime behavior with/without
#    the recording wrappers (§4).
@pytest.mark.anyio
async def test_instrumentation_does_not_change_runtime_semantics(tmp_path: Path) -> None:
    # Instrumented path (recording chat client + recording serializer).
    recorder = CaseEvidenceRecorder()
    instrumented, _, instrumented_fake = _build_runtime(tmp_path, recorder)
    instrumented_result = await _run_one(instrumented, "list customers", "run1_c1")

    # Plain path: same fixtures, plain fake client, default serializer.
    plain_fake = _FakeChatClient()
    plain_dir = tmp_path / "plain"
    plain_dir.mkdir()
    plain_db = _make_db(plain_dir)
    table = CatalogTable(
        table_fqn="db.main.customers",
        service_name="sqlite",
        database_name="db",
        schema_name="main",
        table_name="customers",
        sql_identifier="customers",
        sql_identifier_source="explicit",
        columns=[
            CatalogColumn(
                column_fqn="db.main.customers.name", column_name="name", data_type="TEXT"
            )
        ],
    )
    catalog = InMemoryCatalog()
    catalog.upsert_tables([table])
    documents = CatalogSearchDocumentBuilder().build_search_documents(table)
    plain = assemble_semantic_runtime(
        grounding_context_builder=GroundingContextBuilder(
            catalog=catalog,
            schema_retriever=SchemaRetriever(InMemorySchemaSearch(documents)),
            authorization_service=AuthorizationService(_AllowCustomers()),
        ),
        authorization_service=AuthorizationService(_AllowCustomers()),
        query_executor=SqliteReadOnlyQueryExecutor(plain_db),
        chat_client=plain_fake,
        prompt_directory=PROMPT_DIR,
        execution_policy=QueryExecutionPolicy(
            maximum_result_rows=100, statement_timeout_seconds=10
        ),
        default_dialect="sqlite",
        profile=SemanticRuntimeProfile(model_name="fake-model", temperature=0.0),
        schema_serializer=None,
    )
    plain_result = await _run_one(plain, "list customers", "run1_c1")

    assert instrumented_result.sql == plain_result.sql
    assert instrumented_result.status == plain_result.status
    assert instrumented_result.rows == plain_result.rows
    # The recording client delivered byte-identical prompts to the provider.
    assert instrumented_fake.seen_messages == plain_fake.seen_messages


# 1. exact prompt capture
@pytest.mark.anyio
async def test_exact_prompt_capture(tmp_path: Path) -> None:
    recorder = CaseEvidenceRecorder()
    runtime, _, _ = _build_runtime(tmp_path, recorder)
    await _run_one(runtime, "list customers", "run1_c1")
    evidence = recorder.evidence_for("run1_c1")
    solver_calls = [c for c in evidence.chat_calls if c.schema_name == "sql_candidate"]
    assert solver_calls, "solver call not captured"
    call = solver_calls[-1]
    assert [m.role for m in call.messages] == ["system", "user"]
    assert "authorized" in call.messages[0].content.lower()
    # The exact prompt hash is reproducible from the stored messages.
    assert call.prompt_hash == sha256_json([m.model_dump() for m in call.messages])


# 2. exact final context capture
@pytest.mark.anyio
async def test_exact_final_context_capture(tmp_path: Path) -> None:
    recorder = CaseEvidenceRecorder()
    runtime, _, _ = _build_runtime(tmp_path, recorder)
    await _run_one(runtime, "list customers", "run1_c1")
    evidence = recorder.evidence_for("run1_c1")
    assert evidence.grounding_captures, "grounding not captured"
    capture = evidence.grounding_captures[-1]
    assert "db.main.customers" in capture.selected_tables
    assert "db.main.customers.name" in capture.selected_columns
    assert "customers" in capture.serialized_authorized_schema
    assert capture.serialized_context_hash == sha256_text(capture.serialized_authorized_schema)


# 3. candidate SQL persistence + raw output preserved separately (§9)
@pytest.mark.anyio
async def test_candidate_sql_and_raw_output_persisted(tmp_path: Path) -> None:
    recorder = CaseEvidenceRecorder()
    runtime, db, _ = _build_runtime(tmp_path, recorder)
    result = await _run_one(runtime, "list customers", "run1_c1")
    record = _emitter(tmp_path, recorder).emit(
        case_id="c1",
        db_id="db",
        question="list customers",
        case_run_id="run1_c1",
        runtime_result=result,
        candidate_result_fingerprint=compute_result_fingerprint(result.rows),
        gold_result_fingerprint=None,
        gold_execution_ok=None,
        db_path=str(db),
    )
    assert record.candidate_sql == CANDIDATE_SQL
    assert record.raw_model_output is not None
    assert record.raw_model_output["sql"] == CANDIDATE_SQL
    # Raw output is preserved distinctly from the extracted candidate.
    assert record.raw_model_output_hash == sha256_json(record.raw_model_output)
    assert record.candidate_sql_hash == sha256_text(CANDIDATE_SQL)


# 4. generation failure persistence + state differentiation (§13)
@pytest.mark.anyio
async def test_generation_failure_states_differentiated(tmp_path: Path) -> None:
    recorder = CaseEvidenceRecorder()
    behavior = {"run1_empty": "empty", "run1_provider": "provider_error", "run1_ok": "ok"}
    runtime, db, _ = _build_runtime(tmp_path, recorder, behavior)
    emitter = _emitter(tmp_path, recorder)
    outcomes: dict[str, GenerationOutcome] = {}
    for key in ("run1_ok", "run1_empty", "run1_provider"):
        result = await _run_one(runtime, "list customers", key)
        record = emitter.emit(
            case_id=key,
            db_id="db",
            question="list customers",
            case_run_id=key,
            runtime_result=result,
            candidate_result_fingerprint=(
                compute_result_fingerprint(result.rows)
                if result.status == RuntimeStatus.COMPLETED
                else None
            ),
            gold_result_fingerprint=None,
            gold_execution_ok=None,
            db_path=str(db),
        )
        outcomes[key] = record.generation_outcome
    assert outcomes["run1_ok"] == GenerationOutcome.EXECUTION_SUCCESS
    assert outcomes["run1_empty"] in {
        GenerationOutcome.SQL_EXTRACTION_ERROR,
        GenerationOutcome.GENERATION_EMPTY,
    }
    assert outcomes["run1_provider"] == GenerationOutcome.PROVIDER_ERROR


# 5. replicate identity preservation (§14)
@pytest.mark.anyio
async def test_replicate_identity_preserved(tmp_path: Path) -> None:
    recorder = CaseEvidenceRecorder()
    runtime, db, _ = _build_runtime(tmp_path, recorder)
    records = []
    for replicate in ("r01", "r02"):
        result = await _run_one(runtime, "list customers", f"{replicate}_c1")
        records.append(
            _emitter(tmp_path, recorder, replicate_id=replicate).emit(
                case_id="c1",
                db_id="db",
                question="list customers",
                case_run_id=f"{replicate}_c1",
                runtime_result=result,
                candidate_result_fingerprint=compute_result_fingerprint(result.rows),
                gold_result_fingerprint=None,
                gold_execution_ok=None,
                db_path=str(db),
            )
        )
    assert records[0].case_id == records[1].case_id == "c1"
    assert records[0].replicate_id != records[1].replicate_id
    # Same case, different replicate -> distinct addressable directories.
    assert (
        tmp_path / "evidence" / "exp1" / "cases" / "c1" / "r01" / "evidence_manifest.json"
    ).exists()
    assert (
        tmp_path / "evidence" / "exp1" / "cases" / "c1" / "r02" / "evidence_manifest.json"
    ).exists()


# 6, 7, 8. context / prompt / SQL hash reproducibility
def test_hashes_are_reproducible() -> None:
    assert sha256_text("SELECT 1") == sha256_text("SELECT 1")
    assert sha256_json([{"role": "user", "content": "x"}]) == sha256_json(
        [{"role": "user", "content": "x"}]
    )
    assert sha256_text("a") != sha256_text("b")


# 9. result fingerprint determinism (reused implementation)
def test_result_fingerprint_deterministic() -> None:
    rows = [{"name": "Ada"}, {"name": "Grace"}]
    assert compute_result_fingerprint(rows) == compute_result_fingerprint(list(rows))
    assert compute_result_fingerprint(rows) != compute_result_fingerprint(
        [{"name": "Grace"}, {"name": "Ada"}]
    )


# 10. unknown remains unknown (no fabrication)
@pytest.mark.anyio
async def test_unknown_values_stay_none(tmp_path: Path) -> None:
    recorder = CaseEvidenceRecorder()
    runtime, db, _ = _build_runtime(tmp_path, recorder)
    result = await _run_one(runtime, "list customers", "run1_c1")
    record = _emitter(tmp_path, recorder).emit(
        case_id="c1",
        db_id="db",
        question="list customers",
        case_run_id="run1_c1",
        runtime_result=result,
        candidate_result_fingerprint=compute_result_fingerprint(result.rows),
        gold_result_fingerprint=None,
        gold_execution_ok=None,
        db_path=str(db),
    )
    assert record.gold_sql is None
    assert record.gold_fingerprint is None
    assert record.seed_or_null is None


# 11. evidence completeness classification
def test_completeness_classification() -> None:
    assert (
        classify_evidence_completeness(
            has_exact_prompt=True,
            has_exact_context=True,
            has_candidate_or_explicit_failure=True,
            has_model_config=True,
            has_execution_record=True,
            has_provenance=True,
        )
        == EvidenceCompleteness.COMPLETE
    )
    assert (
        classify_evidence_completeness(
            has_exact_prompt=True,
            has_exact_context=True,
            has_candidate_or_explicit_failure=False,
            has_model_config=True,
            has_execution_record=True,
            has_provenance=True,
        )
        == EvidenceCompleteness.INSUFFICIENT
    )
    assert (
        classify_evidence_completeness(
            has_exact_prompt=True,
            has_exact_context=True,
            has_candidate_or_explicit_failure=True,
            has_model_config=False,
            has_execution_record=True,
            has_provenance=True,
        )
        == EvidenceCompleteness.PARTIAL
    )


# 12. replay without LLM call
@pytest.mark.anyio
async def test_replay_is_read_only_no_llm(tmp_path: Path) -> None:
    recorder = CaseEvidenceRecorder()
    runtime, db, fake = _build_runtime(tmp_path, recorder)
    result = await _run_one(runtime, "list customers", "run1_c1")
    _emitter(tmp_path, recorder).emit(
        case_id="c1",
        db_id="db",
        question="list customers",
        case_run_id="run1_c1",
        runtime_result=result,
        candidate_result_fingerprint=compute_result_fingerprint(result.rows),
        gold_result_fingerprint=None,
        gold_execution_ok=None,
        db_path=str(db),
    )
    calls_before = len(fake.calls)
    reloaded = load_case_record(tmp_path / "evidence", "exp1", "c1", "r01")
    assert reloaded.candidate_sql == CANDIDATE_SQL
    assert reloaded.exact_solver_prompt  # reconstructable
    assert len(fake.calls) == calls_before  # replay made no provider call
    assert all_hashes_valid(reloaded)


# 13. no secret capture
@pytest.mark.anyio
async def test_no_secret_captured(tmp_path: Path) -> None:
    recorder = CaseEvidenceRecorder()
    runtime, db, _ = _build_runtime(tmp_path, recorder)
    result = await _run_one(runtime, "list customers", "run1_c1")
    record = _emitter(tmp_path, recorder).emit(
        case_id="c1",
        db_id="db",
        question="list customers",
        case_run_id="run1_c1",
        runtime_result=result,
        candidate_result_fingerprint=compute_result_fingerprint(result.rows),
        gold_result_fingerprint=None,
        gold_execution_ok=None,
        db_path=str(db),
    )
    blob = record.model_dump_json()
    assert "Authorization" not in blob
    assert "Bearer " not in blob
    assert "api_key" not in blob.lower()


# 14. no gold content entering evidence artifacts
@pytest.mark.anyio
async def test_no_gold_in_evidence(tmp_path: Path) -> None:
    gold_sql = "SELECT secret_gold FROM private_table"
    recorder = CaseEvidenceRecorder()
    runtime, db, _ = _build_runtime(tmp_path, recorder)
    result = await _run_one(runtime, "list customers", "run1_c1")
    record = _emitter(tmp_path, recorder).emit(
        case_id="c1",
        db_id="db",
        question="list customers",
        case_run_id="run1_c1",
        runtime_result=result,
        candidate_result_fingerprint=compute_result_fingerprint(result.rows),
        gold_result_fingerprint="fingerprint-only",
        gold_execution_ok=True,
        db_path=str(db),
    )
    # Gold text is never handed to the harness, so it cannot appear anywhere.
    write_case_record(tmp_path / "evidence", record)
    for path in (tmp_path / "evidence" / "exp1" / "cases" / "c1" / "r01").glob("*.json"):
        assert gold_sql not in path.read_text(encoding="utf-8")
    assert record.gold_sql is None
    # Fingerprint-only gold reference is allowed.
    assert record.gold_fingerprint == "fingerprint-only"


# 16. dirty / config mismatch invalidation
def test_config_mismatch_is_detectable(tmp_path: Path) -> None:
    p1 = SemanticRuntimeProfile(model_name="m", temperature=0.0)
    p2 = SemanticRuntimeProfile(model_name="m", temperature=0.0, planner_mode="deterministic")
    assert grounding_config_hash(p1) != grounding_config_hash(p2)


# hash corruption detection (§18)
def test_hash_corruption_detected() -> None:
    from t2s.benchmark.case_evidence.contract import CaseRunRecord, ChatMessageRecord

    record = CaseRunRecord(
        experiment_id="e",
        run_id="r",
        replicate_id="r01",
        case_id="c1",
        candidate_sql="SELECT 1",
        candidate_sql_hash=sha256_text("SELECT 1"),
        exact_solver_prompt=[ChatMessageRecord(role="user", content="hi")],
        solver_prompt_hash=sha256_json([{"role": "user", "content": "hi"}]),
    )
    assert all_hashes_valid(record)
    tampered = record.model_copy(update={"candidate_sql": "SELECT 2"})
    checks = {c.field: c.ok for c in verify_record_hashes(tampered)}
    assert checks["candidate_sql_hash"] is False
