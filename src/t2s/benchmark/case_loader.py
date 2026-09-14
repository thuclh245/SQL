import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class InferenceBenchmarkCase:
    """Fields allowed to enter runtime inference."""

    case_id: str
    question_id: int | None
    db_id: str
    question: str
    evidence: str | None
    bird_difficulty: str | None
    t2s_stratum: str | None


@dataclass(frozen=True)
class ScoringGold:
    official_sql: str | None
    curated_sql: str | None


@dataclass(frozen=True)
class BenchmarkCaseBundle:
    inference_case: InferenceBenchmarkCase
    scoring_gold: ScoringGold


@dataclass(frozen=True)
class BenchmarkCaseFilter:
    limit: int | None = None
    case_ids: frozenset[str] = frozenset()
    db_ids: frozenset[str] = frozenset()


def load_benchmark_cases(
    dataset_path: Path,
    case_filter: BenchmarkCaseFilter | None = None,
) -> list[BenchmarkCaseBundle]:
    active_filter = case_filter or BenchmarkCaseFilter()
    cases: list[BenchmarkCaseBundle] = []
    for raw_case in _read_jsonl(dataset_path):
        bundle = _parse_case_bundle(raw_case)
        if active_filter.case_ids and bundle.inference_case.case_id not in active_filter.case_ids:
            continue
        if active_filter.db_ids and bundle.inference_case.db_id not in active_filter.db_ids:
            continue
        cases.append(bundle)
        if active_filter.limit is not None and len(cases) >= active_filter.limit:
            break
    return cases


def _read_jsonl(dataset_path: Path) -> list[dict[str, Any]]:
    if not dataset_path.exists():
        raise FileNotFoundError(f"Benchmark dataset not found: {dataset_path}")
    rows: list[dict[str, Any]] = []
    with dataset_path.open("r", encoding="utf-8") as dataset_file:
        for line_number, line in enumerate(dataset_file, start=1):
            if not line.strip():
                continue
            try:
                raw_case = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Benchmark dataset has invalid JSON on line {line_number}: {dataset_path}"
                ) from exc
            if not isinstance(raw_case, dict):
                raise ValueError(
                    f"Benchmark case on line {line_number} must be a JSON object."
                )
            rows.append(raw_case)
    return rows


def _parse_case_bundle(raw_case: dict[str, Any]) -> BenchmarkCaseBundle:
    inference = raw_case.get("inference")
    if not isinstance(inference, dict):
        raise ValueError(f"Case {raw_case.get('case_id')} is missing inference object.")

    case_id = str(raw_case.get("case_id") or raw_case.get("pilot_id") or "")
    if not case_id:
        raise ValueError("Benchmark case is missing case_id.")

    question = inference.get("question") or raw_case.get("question")
    db_id = inference.get("db_id") or raw_case.get("db_id")
    if not isinstance(question, str) or not question.strip():
        raise ValueError(f"Case {case_id} is missing inference question.")
    if not isinstance(db_id, str) or not db_id.strip():
        raise ValueError(f"Case {case_id} is missing inference db_id.")

    source = raw_case.get("source")
    question_id = raw_case.get("question_id")
    if question_id is None and isinstance(source, dict):
        question_id = source.get("question_id")

    gold = raw_case.get("gold")
    if not isinstance(gold, dict):
        gold = {}
    official_sql = raw_case.get("bird_gold_sql") or gold.get("sql_original")
    curated_sql = gold.get("sql_corrected")

    return BenchmarkCaseBundle(
        inference_case=InferenceBenchmarkCase(
            case_id=case_id,
            question_id=int(question_id) if question_id is not None else None,
            db_id=db_id.strip(),
            question=question.strip(),
            evidence=_optional_str(inference.get("evidence") or raw_case.get("evidence")),
            bird_difficulty=_optional_str(
                raw_case.get("bird_difficulty") or gold.get("bird_difficulty")
            ),
            t2s_stratum=_optional_str(raw_case.get("t2s_stratum") or gold.get("stratum")),
        ),
        scoring_gold=ScoringGold(
            official_sql=_optional_str(official_sql),
            curated_sql=_optional_str(curated_sql),
        ),
    )


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    stripped_value = value.strip()
    return stripped_value or None
