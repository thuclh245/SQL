from collections import Counter, defaultdict
from statistics import median
from typing import Any


def aggregate_benchmark_metrics(case_results: list[dict[str, Any]]) -> dict[str, Any]:
    total_cases = len(case_results)
    correct_cases = sum(1 for result in case_results if result["execution_correct"] is True)
    completed_cases = sum(1 for result in case_results if result["runtime_status"] == "SUCCESS")
    latencies = [
        float(result["latency_ms"])
        for result in case_results
        if result.get("latency_ms") is not None
    ]

    by_stratum = _slice_execution_accuracy(case_results, "t2s_stratum")
    by_difficulty = _slice_execution_accuracy(case_results, "bird_difficulty")
    by_database = _slice_execution_accuracy(case_results, "db_id")

    db_percentages = [
        slice_metrics["percentage"]
        for slice_metrics in by_database.values()
        if slice_metrics["total"] > 0
    ]
    status_counter = Counter(result["runtime_status"] for result in case_results)
    escalated_results = [result for result in case_results if result.get("escalated") is True]

    return {
        "overall": {
            "case_count": total_cases,
            "execution_accuracy": _ratio(correct_cases, total_cases),
            "correct": correct_cases,
            "total": total_cases,
            "successful_execution_rate": _ratio(completed_cases, total_cases),
        },
        "by_t2s_stratum": by_stratum,
        "by_bird_difficulty": by_difficulty,
        "by_database": by_database,
        "macro_db_execution_accuracy": (
            round(sum(db_percentages) / len(db_percentages), 4) if db_percentages else 0.0
        ),
        "p5": {
            "escalation_rate": _ratio(len(escalated_results), total_cases),
            "success_after_escalation": _ratio(
                sum(1 for result in escalated_results if result["execution_correct"] is True),
                len(escalated_results),
            ),
            "same_context_stop_rate": _ratio(
                sum(1 for result in escalated_results if result.get("same_context_stop")),
                len(escalated_results),
            ),
            "avg_grounding_calls": _average_nullable(case_results, "grounding_calls"),
            "avg_solver_calls": _average_nullable(case_results, "solver_calls"),
        },
        "runtime": {
            "status_breakdown": dict(status_counter),
            "safety_rejections": status_counter.get("SAFETY_REJECTED", 0),
            "access_rejections": status_counter.get("ACCESS_DENIED", 0),
            "execution_failures": status_counter.get("EXECUTION_FAILED", 0),
            "timeouts": status_counter.get("TIMEOUT", 0),
        },
        "cost_performance": {
            "avg_latency_ms": round(sum(latencies) / len(latencies), 3) if latencies else None,
            "p50_latency_ms": round(float(median(latencies)), 3) if latencies else None,
            "p95_latency_ms": _percentile(latencies, 0.95),
            "avg_input_tokens": _average_nullable(case_results, "tokens_input"),
            "avg_output_tokens": _average_nullable(case_results, "tokens_output"),
            "avg_llm_calls": _average_nullable(case_results, "solver_calls"),
        },
        "abstention": _build_abstention_metrics(case_results),
        "value_linking": _build_value_linking_metrics(case_results),
    }


def _build_abstention_metrics(case_results: list[dict[str, Any]]) -> dict[str, Any]:
    """Separate "produced no SQL" from "produced wrong SQL".

    Execution accuracy alone conflates the two, which hides whether a change moved
    generation quality or only moved the abstention threshold.
    """
    total_cases = len(case_results)
    sql_produced = [result for result in case_results if result.get("generated_sql")]
    executed = [result for result in case_results if result.get("execution_success") is True]
    correct_among_executed = sum(1 for result in executed if result["execution_correct"] is True)
    status_counter = Counter(result["runtime_status"] for result in case_results)
    outcome_counter = Counter(
        str(result.get("orchestration_outcome")) for result in case_results
    )
    return {
        "sql_produced_rate": _ratio(len(sql_produced), total_cases),
        "unresolved_rate": _ratio(status_counter.get("UNRESOLVED", 0), total_cases),
        "execution_success_rate": _ratio(len(executed), total_cases),
        "precision_among_executed": _ratio(correct_among_executed, len(executed)),
        "resolved_with_caveats_count": outcome_counter.get("resolved_with_caveats", 0),
    }


def _build_value_linking_metrics(case_results: list[dict[str, Any]]) -> dict[str, Any]:
    """Report value-grounding reach, adoption and cost.

    Hit rate is measured over cases that were actually probed, so a run with value
    grounding switched off reports zeros rather than a misleading denominator.
    """
    total_cases = len(case_results)
    probed = [result for result in case_results if int(result.get("value_probe_count") or 0) > 0]
    with_bindings = [
        result for result in probed if int(result.get("value_binding_count") or 0) > 0
    ]
    using_evidence = [
        result for result in case_results if result.get("candidate_uses_value_evidence") is True
    ]
    probe_counts = [int(result.get("value_probe_count") or 0) for result in case_results]
    grounding_latencies = [
        float(result.get("value_grounding_latency_ms") or 0.0) for result in case_results
    ]
    binding_counts = [int(result.get("value_binding_count") or 0) for result in case_results]
    not_using_evidence = [
        result for result in case_results if result.get("candidate_uses_value_evidence") is not True
    ]
    return {
        "probed_case_count": len(probed),
        "value_link_hit_rate": _ratio(len(with_bindings), len(probed)),
        "avg_bindings_per_query": (
            round(sum(binding_counts) / total_cases, 4) if total_cases else 0.0
        ),
        "queries_using_value_evidence": len(using_evidence),
        "queries_using_value_evidence_rate": _ratio(len(using_evidence), total_cases),
        "avg_value_probes_per_query": (
            round(sum(probe_counts) / total_cases, 4) if total_cases else 0.0
        ),
        "max_value_probes_per_query": max(probe_counts) if probe_counts else 0,
        "avg_value_grounding_latency_ms": (
            round(sum(grounding_latencies) / total_cases, 3) if total_cases else 0.0
        ),
        "max_value_grounding_latency_ms": (
            round(max(grounding_latencies), 3) if grounding_latencies else 0.0
        ),
        "accuracy_when_value_evidence_used": _ratio(
            sum(1 for result in using_evidence if result["execution_correct"] is True),
            len(using_evidence),
        ),
        "accuracy_when_value_evidence_unused": _ratio(
            sum(1 for result in not_using_evidence if result["execution_correct"] is True),
            len(not_using_evidence),
        ),
    }


def _slice_execution_accuracy(
    case_results: list[dict[str, Any]],
    key: str,
) -> dict[str, dict[str, Any]]:
    grouped_results: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for result in case_results:
        grouped_results[str(result.get(key) or "unknown")].append(result)

    return {
        group_value: {
            "correct": sum(1 for result in grouped if result["execution_correct"] is True),
            "total": len(grouped),
            "percentage": _ratio(
                sum(1 for result in grouped if result["execution_correct"] is True),
                len(grouped),
            ),
        }
        for group_value, grouped in sorted(grouped_results.items())
    }


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _average_nullable(case_results: list[dict[str, Any]], key: str) -> float | None:
    values: list[float] = []
    for result in case_results:
        value = result.get(key)
        if value is None:
            continue
        values.append(float(value))
    if not values:
        return None
    return round(sum(values) / len(values), 3)


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    sorted_values = sorted(values)
    index = min(len(sorted_values) - 1, int(round((len(sorted_values) - 1) * percentile)))
    return round(sorted_values[index], 3)
