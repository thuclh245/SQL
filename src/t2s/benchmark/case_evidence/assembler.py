"""Assemble a :class:`CaseRunRecord` from runtime output + recorded evidence.

This is observational glue: it reads the runtime result and the captured chat /
grounding evidence and produces the canonical record. It never mutates runtime
state and never fabricates values — absent inputs stay ``None`` (E04 §6).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from t2s.benchmark.case_evidence.contract import (
    CaseRunRecord,
    ChatCallRecord,
    GenerationOutcome,
    classify_evidence_completeness,
)
from t2s.benchmark.case_evidence.hashing import sha256_json, sha256_text
from t2s.benchmark.case_evidence.recorder import CaseChatEvidence
from t2s.runtime import RuntimeExecutionResult, RuntimeStatus


def _final_solver_call(evidence: CaseChatEvidence) -> ChatCallRecord | None:
    solver_calls = [call for call in evidence.chat_calls if call.schema_name == "sql_candidate"]
    if solver_calls:
        return solver_calls[-1]
    return evidence.chat_calls[-1] if evidence.chat_calls else None


def _classify_generation_outcome(
    runtime_result: RuntimeExecutionResult,
    evidence: CaseChatEvidence,
) -> GenerationOutcome:
    status = runtime_result.status
    if status == RuntimeStatus.COMPLETED:
        return GenerationOutcome.EXECUTION_SUCCESS
    if status == RuntimeStatus.EXECUTION_FAILED:
        return GenerationOutcome.EXECUTION_ERROR
    if status in {RuntimeStatus.SAFETY_REJECTED, RuntimeStatus.ACCESS_DENIED}:
        return GenerationOutcome.VALIDATION_REJECTED
    if status == RuntimeStatus.UNRESOLVED:
        return GenerationOutcome.ABSTAIN
    if status == RuntimeStatus.TIMEOUT:
        return GenerationOutcome.PROVIDER_ERROR
    if status == RuntimeStatus.GENERATION_FAILED:
        # Distinguish a provider error from an empty/malformed generation using
        # the captured chat-call evidence.
        final_call = _final_solver_call(evidence)
        if final_call is not None and final_call.error_class is not None:
            return GenerationOutcome.PROVIDER_ERROR
        if final_call is not None and not final_call.extracted_sql:
            return GenerationOutcome.SQL_EXTRACTION_ERROR
        return GenerationOutcome.GENERATION_EMPTY
    return GenerationOutcome.UNKNOWN


def _validation_outputs(runtime_result: RuntimeExecutionResult) -> dict[str, Any]:
    trace = runtime_result.trace
    outputs: dict[str, Any] = {
        "safety_passed": trace.safety_check_passed,
        "access_passed": trace.access_check_passed,
        "execution_passed": trace.execution_passed,
    }
    if trace.verifier_outcome is not None:
        outputs["verifier"] = trace.verifier_outcome.model_dump()
    if trace.validator_outcome is not None:
        outputs["validator"] = trace.validator_outcome.model_dump()
    if runtime_result.result_verification_outcome is not None:
        rv = runtime_result.result_verification_outcome
        outputs["result_verification"] = {
            "decision": getattr(getattr(rv, "decision", None), "value", None),
            "is_suspicious": getattr(rv, "is_suspicious", None),
            "failure_code": getattr(rv, "failure_code", None),
        }
    return outputs


def build_case_run_record(
    *,
    experiment_id: str,
    run_id: str,
    replicate_id: str,
    case_id: str,
    db_id: str | None,
    question: str | None,
    evidence: CaseChatEvidence,
    runtime_result: RuntimeExecutionResult,
    candidate_result_fingerprint: str | None,
    gold_result_fingerprint: str | None,
    gold_execution_ok: bool | None,
    dataset_name: str | None,
    dataset_split: str | None,
    dataset_version_or_hash: str | None,
    source_commit: str | None,
    source_dirty: bool | None,
    grounding_strategy: str | None,
    grounding_config_hash: str | None,
    prompt_version: str | None,
    provider: str | None,
    model: str | None,
    temperature: float | None,
    seed_or_null: int | None,
    retry_policy: dict[str, Any] | None,
    correction_budget: int | None,
    validator_mode: str | None,
    verifier_mode: str | None,
    request_id: str | None = None,
    trace_id: str | None = None,
    db_path: str | None = None,
    created_at: str | None = None,
) -> CaseRunRecord:
    """Fuse runtime output + recorded evidence into a canonical record."""

    final_grounding = evidence.grounding_captures[-1] if evidence.grounding_captures else None
    final_call = _final_solver_call(evidence)

    exact_context = final_grounding.serialized_authorized_schema if final_grounding else None
    grounded_context_hash = (
        final_grounding.serialized_context_hash if final_grounding else None
    )

    exact_prompt = list(final_call.messages) if final_call else []
    solver_prompt_hash = (
        sha256_json([m.model_dump() for m in exact_prompt]) if exact_prompt else None
    )

    candidate_sql = runtime_result.sql
    candidate_sql_hash = sha256_text(candidate_sql) if candidate_sql else None
    raw_model_output = final_call.raw_model_output if final_call else None
    raw_model_output_hash = final_call.raw_model_output_hash if final_call else None

    generation_outcome = _classify_generation_outcome(runtime_result, evidence)

    trace = runtime_result.trace
    orchestration_trace = trace.orchestration_trace
    ast_summary = {"ast_referenced_tables": list(trace.ast_referenced_tables)}
    validation_outputs = _validation_outputs(runtime_result)

    execution_attempted = trace.execution_passed or (
        runtime_result.status
        in {RuntimeStatus.COMPLETED, RuntimeStatus.EXECUTION_FAILED}
    )
    execution_status = (
        "SUCCESS"
        if runtime_result.status == RuntimeStatus.COMPLETED
        else runtime_result.status.value.upper()
    )
    execution_error_class = (
        runtime_result.status.value if runtime_result.status != RuntimeStatus.COMPLETED else None
    )

    candidate_columns = list(runtime_result.columns) if runtime_result.columns else None
    candidate_row_count = (
        runtime_result.row_count if runtime_result.status == RuntimeStatus.COMPLETED else None
    )

    completeness = classify_evidence_completeness(
        has_exact_prompt=bool(exact_prompt),
        has_exact_context=exact_context is not None,
        # Either an extracted candidate exists, or an explicit generation-failure
        # state is recorded (E04 §12/§13).
        has_candidate_or_explicit_failure=bool(candidate_sql)
        or generation_outcome
        in {
            GenerationOutcome.PROVIDER_ERROR,
            GenerationOutcome.GENERATION_EMPTY,
            GenerationOutcome.SQL_EXTRACTION_ERROR,
            GenerationOutcome.VALIDATION_REJECTED,
            GenerationOutcome.ABSTAIN,
            GenerationOutcome.EXECUTION_ERROR,
        },
        has_model_config=bool(model) and provider is not None,
        has_execution_record=execution_status is not None,
        has_provenance=source_commit is not None or dataset_name is not None,
    )

    selected_tables = final_grounding.selected_tables if final_grounding else []
    if not selected_tables and orchestration_trace is not None:
        selected_tables = list(orchestration_trace.final_table_fqns)

    return CaseRunRecord(
        experiment_id=experiment_id,
        run_id=run_id,
        replicate_id=replicate_id,
        case_id=case_id,
        db_id=db_id,
        question=question,
        dataset_name=dataset_name,
        dataset_split=dataset_split,
        dataset_version_or_hash=dataset_version_or_hash,
        source_commit=source_commit,
        source_dirty=source_dirty,
        grounding_strategy=grounding_strategy,
        grounding_config_hash=grounding_config_hash,
        selected_tables=selected_tables,
        selected_columns=final_grounding.selected_columns if final_grounding else [],
        selected_relationships=final_grounding.selected_relationships if final_grounding else [],
        exact_grounded_context=exact_context,
        grounded_context_hash=grounded_context_hash,
        evidence_context=exact_context,
        grounding_captures=list(evidence.grounding_captures),
        prompt_version=prompt_version,
        exact_solver_prompt=exact_prompt,
        solver_prompt_hash=solver_prompt_hash,
        chat_calls=list(evidence.chat_calls),
        provider=provider,
        model=model,
        temperature=temperature,
        seed_or_null=seed_or_null,
        retry_policy=retry_policy,
        correction_budget=correction_budget,
        candidate_sql=candidate_sql,
        candidate_sql_hash=candidate_sql_hash,
        raw_model_output=raw_model_output,
        raw_model_output_hash=raw_model_output_hash,
        solver_assumptions=list(trace.candidate_assumptions),
        solver_unresolved_items=(
            list(orchestration_trace.baseline_unresolved_codes)
            if orchestration_trace is not None
            else []
        ),
        generation_outcome=generation_outcome,
        validator_mode=validator_mode,
        verifier_mode=verifier_mode,
        ast_summary=ast_summary,
        validation_outputs=validation_outputs,
        execution_attempted=execution_attempted,
        execution_status=execution_status,
        execution_error_class=execution_error_class,
        runtime_status=execution_status,
        candidate_execution_ok=trace.execution_passed,
        candidate_result_schema=candidate_columns,
        candidate_result_row_count=candidate_row_count,
        candidate_result_fingerprint=candidate_result_fingerprint,
        candidate_fingerprint=candidate_result_fingerprint,
        gold_sql=None,
        gold_result=None,
        gold_result_fingerprint=gold_result_fingerprint,
        gold_fingerprint=gold_result_fingerprint,
        gold_execution_ok=gold_execution_ok,
        latency_breakdown={
            "total_latency_ms": runtime_result.total_latency_ms,
            "execution_time_ms": runtime_result.execution_time_ms,
            "solver_elapsed_ms": final_call.elapsed_ms if final_call else None,
        },
        request_id=request_id,
        trace_id=trace_id,
        db_path=db_path,
        created_at=created_at or datetime.now(UTC).isoformat(),
        evidence_completeness=completeness,
    )
