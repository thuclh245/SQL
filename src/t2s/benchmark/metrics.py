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
