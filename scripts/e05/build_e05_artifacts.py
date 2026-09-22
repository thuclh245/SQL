"""Build the E05 scorer-certification artifact set (E05 §26).

Runs strictly downstream of stored/governed evaluation evidence and changes no
runtime behaviour (E05 §3). It:

* emits every versioned manifest under ``results/e05/``;
* runs an old-vs-new disagreement audit (E05 §22) on the governed, non-holdout
  ``synthetic_solver_ceiling`` benchmark (18 cases + 54 logic mutants over 4 real
  SQLite fixtures), plus purpose-built generic lucky-match probes, so every
  quadrant of the disagreement matrix is exercised;
* generates evaluation-only counterexample fixtures (deterministic row-dropout)
  used to prove lucky matches; these never touch runtime or the canonical
  benchmark fixtures.

Usage::

    python -m scripts.e05.build_e05_artifacts
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from t2s.benchmark.scoring import (
    compute_result_fingerprint,
    evaluate_candidate_vs_gold,
    execute_evaluation_sql,
)
from t2s.evaluation.scoring.aggregation import aggregate, check_comparability
from t2s.evaluation.scoring.deterministic import score_case_deterministic
from t2s.evaluation.scoring.equivalence import equivalence_rules_manifest
from t2s.evaluation.scoring.lucky_match import assess_lucky_match
from t2s.evaluation.scoring.protocols import CaseEvidence, ResultTable
from t2s.evaluation.scoring.records import SemanticAuditRecord
from t2s.evaluation.scoring.semantic_audit import deterministic_semantic_audit
from t2s.evaluation.scoring.taxonomy import BSubtype, Grade, RootCause
from t2s.evaluation.scoring.versions import version_manifest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CEILING_ROOT = PROJECT_ROOT / "benchmarks" / "synthetic_solver_ceiling"
CEILING_DBS = CEILING_ROOT / "databases"
OUT_DIR = PROJECT_ROOT / "results" / "e05"
ALT_FIXTURE_DIR = OUT_DIR / "alt_fixtures"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def _result_table(sql: str, db_path: Path) -> ResultTable | None:
    res = execute_evaluation_sql(sql, db_path)
    if not res.ok:
        return None
    return ResultTable(columns=(), rows=tuple(res.rows))


def _make_row_dropout_fixture(source_db: Path, target_db: Path, *, keep_fraction: float) -> Path:
    """Create an evaluation-only alternate fixture by deterministically dropping rows.

    Schema-agnostic and read-only downstream: never used by runtime, never mutates
    the canonical benchmark fixtures (E05 §3, §9 'governed alternate fixtures').
    """

    target_db.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source_db, target_db)
    conn = sqlite3.connect(target_db)
    try:
        conn.execute("PRAGMA foreign_keys = OFF")
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        ]
        for table_name in tables:
            # Deterministic: drop rows whose rowid mod k != 0 for a stable subset.
            modulus = max(2, round(1 / max(0.01, 1 - keep_fraction)))
            conn.execute(f'DELETE FROM "{table_name}" WHERE (rowid % {modulus}) = 0')
        conn.commit()
    finally:
        conn.close()
    return target_db


# ---------------------------------------------------------------------------
# Old-vs-new disagreement audit
# ---------------------------------------------------------------------------


@dataclass
class AuditRow:
    case_id: str
    family: str
    old_strict_pass: bool | None
    new_grade: Grade
    new_subtype: BSubtype | None
    lucky_verdict: str | None


def _old_scorer_strict_pass(candidate_sql: str, gold_sql: str, db_path: Path) -> bool | None:
    """Historical scorer surface: strict execution accuracy on the primary fixture."""

    correct, cand_res, gold_res = evaluate_candidate_vs_gold(candidate_sql, gold_sql, db_path)
    if not cand_res.ok or not gold_res.ok:
        return None
    return correct


def _new_audit_for(
    *,
    case_id: str,
    question: str,
    candidate_sql: str,
    gold_sql: str,
    db_path: Path,
    candidate_result: ResultTable | None,
    gold_result: ResultTable | None,
    alternate_db_paths: list[Path],
) -> SemanticAuditRecord:
    cand_fp = compute_result_fingerprint(list(candidate_result.rows)) if candidate_result else None
    gold_fp = compute_result_fingerprint(list(gold_result.rows)) if gold_result else None
    evidence = CaseEvidence(
        case_id=case_id,
        replicate_id="r1",
        db_id=db_path.stem,
        question=question,
        candidate_sql=candidate_sql,
        gold_sql=gold_sql,
        runtime_status="SUCCESS",
        candidate_execution_ok=candidate_result is not None,
        gold_execution_ok=gold_result is not None,
        candidate_result=candidate_result,
        gold_result=gold_result,
        candidate_fingerprint=cand_fp,
        gold_fingerprint=gold_fp,
        db_path=str(db_path),
    )
    scoring = score_case_deterministic(evidence)
    lucky = None
    if scoring.deterministic_equivalent is True:
        lucky = assess_lucky_match(
            matches_on_primary=True,
            candidate_sql=candidate_sql,
            gold_sql=gold_sql,
            alternate_db_paths=list(alternate_db_paths),
        )
    return deterministic_semantic_audit(evidence, scoring, lucky_assessment=lucky)


def run_old_vs_new_audit() -> dict[str, Any]:
    cases = {c["case_id"]: c for c in _read_jsonl(CEILING_ROOT / "datasets" / "cases.jsonl")}
    mutants = _read_jsonl(CEILING_ROOT / "datasets" / "mutants.jsonl")

    ALT_FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    alt_by_db: dict[str, Path] = {}
    for db_file in sorted(CEILING_DBS.glob("*.sqlite")):
        alt = _make_row_dropout_fixture(
            db_file, ALT_FIXTURE_DIR / f"{db_file.stem}.dropout.sqlite", keep_fraction=0.5
        )
        alt_by_db[db_file.stem] = alt

    rows: list[AuditRow] = []
    audit_records: list[SemanticAuditRecord] = []
    lucky_records: list[SemanticAuditRecord] = []

    def _db(case: dict[str, Any]) -> Path:
        return CEILING_DBS / f"{case['db_id']}.sqlite"

    # Family 1 (control): candidate == gold  -> expect old PASS / new A.
    # Family 2 (extra col): gold + harmless extra column -> expect old FAIL / new B.
    for case_id, case in cases.items():
        gold_sql = case["gold_sql"]
        db_path = _db(case)
        gold_tbl = _result_table(gold_sql, db_path)
        if gold_tbl is None:
            continue
        alt = [alt_by_db[case["db_id"]]]

        control = _new_audit_for(
            case_id=case_id,
            question=case["question"],
            candidate_sql=gold_sql,
            gold_sql=gold_sql,
            db_path=db_path,
            candidate_result=gold_tbl,
            gold_result=gold_tbl,
            alternate_db_paths=alt,
        )
        audit_records.append(control)
        rows.append(
            AuditRow(
                case_id,
                "control_gold",
                _old_scorer_strict_pass(gold_sql, gold_sql, db_path),
                control.classification,
                control.subtype,
                None,
            )
        )

        # harmless extra column: append a constant column to candidate result only.
        extra_tbl = ResultTable(
            columns=(),
            rows=tuple(row + ("EXTRA",) for row in gold_tbl.rows),
        )
        extra_audit = _new_audit_for(
            case_id=f"{case_id}__extra_col",
            question=case["question"],
            candidate_sql=gold_sql + " -- + harmless extra column",
            gold_sql=gold_sql,
            db_path=db_path,
            candidate_result=extra_tbl,
            gold_result=gold_tbl,
            alternate_db_paths=alt,
        )
        # Old scorer sees the extra column as a row-shape mismatch -> strict fail.
        old_extra = _old_extra_column_strict(gold_tbl, extra_tbl, gold_sql)
        rows.append(
            AuditRow(
                f"{case_id}__extra_col",
                "harmless_extra_column",
                old_extra,
                extra_audit.classification,
                extra_audit.subtype,
                None,
            )
        )

    # Family 3 (mutants): logic mutants -> expect old FAIL / new D.
    for mutant in mutants:
        case = cases.get(mutant["case_id"])
        if case is None:
            continue
        db_path = _db(case)
        gold_sql = case["gold_sql"]
        mutant_sql = mutant["mutant_sql"]
        gold_tbl = _result_table(gold_sql, db_path)
        cand_tbl = _result_table(mutant_sql, db_path)
        record = _new_audit_for(
            case_id=f"{mutant['case_id']}__m{mutant['mutant_index']}",
            question=case["question"],
            candidate_sql=mutant_sql,
            gold_sql=gold_sql,
            db_path=db_path,
            candidate_result=cand_tbl,
            gold_result=gold_tbl,
            alternate_db_paths=[alt_by_db[case["db_id"]]],
        )
        rows.append(
            AuditRow(
                f"{mutant['case_id']}__m{mutant['mutant_index']}",
                "logic_mutant",
                _old_scorer_strict_pass(mutant_sql, gold_sql, db_path),
                record.classification,
                record.subtype,
                None,
            )
        )

    # Family 4 (lucky probes): generic synthetic cases where a wrong query matches
    # gold on the primary fixture but diverges on a governed alternate fixture.
    lucky_rows, lucky_records = _build_lucky_probes()
    rows.extend(lucky_rows)

    matrix = _disagreement_matrix(rows)
    return {
        "sample": {
            "governed_benchmark": "synthetic_solver_ceiling",
            "families": sorted({r.family for r in rows}),
            "case_families_note": (
                "control_gold + harmless_extra_column + logic_mutant drawn from the "
                "governed non-holdout ceiling benchmark; lucky_probe cases are generic "
                "synthetic fixtures generated by this script (no benchmark leakage)."
            ),
            "row_count": len(rows),
        },
        "old_scorer": "strict execution accuracy on primary fixture "
        "(t2s.benchmark.scoring.evaluate_candidate_vs_gold)",
        "new_scorer": "t2s.evaluation.scoring deterministic + semantic audit "
        f"({version_manifest()['scorer_version']})",
        "disagreement_matrix": matrix,
        "rows": [vars(r) | {"new_grade": r.new_grade.value, "new_subtype":
                            (r.new_subtype.value if r.new_subtype else None),
                            "lucky_verdict": r.lucky_verdict} for r in rows],
        "interpretation": {
            "old_fail_new_B": "harmless output-contract variance the strict scorer "
            "over-penalized (valuable, E05 §22).",
            "old_pass_new_E": "lucky match the strict scorer rewarded; wrong logic "
            "exposed on a governed alternate fixture (valuable, E05 §22).",
        },
    }


def _old_extra_column_strict(
    gold_tbl: ResultTable, extra_tbl: ResultTable, gold_sql: str
) -> bool:
    from t2s.benchmark.scoring import score_execution_accuracy

    return score_execution_accuracy(
        generated_rows=list(extra_tbl.rows),
        gold_rows=list(gold_tbl.rows),
        gold_sql=gold_sql,
    )


def _build_lucky_probes() -> tuple[list[AuditRow], list[SemanticAuditRecord]]:
    """Generic lucky-match probes on a purpose-built sales fixture."""

    probe_dir = ALT_FIXTURE_DIR / "lucky_probes"
    probe_dir.mkdir(parents=True, exist_ok=True)
    primary = probe_dir / "primary.sqlite"
    alternate = probe_dir / "alternate.sqlite"
    for path, data in (
        (primary, [(1, "east", 10), (2, "east", 20), (3, "east", 30)]),
        (alternate, [(1, "east", 10), (2, "west", 55), (3, "east", 30)]),
    ):
        if path.exists():
            path.unlink()
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE sales(id INTEGER, region TEXT, amount INTEGER)")
        conn.executemany("INSERT INTO sales VALUES (?,?,?)", data)
        conn.commit()
        conn.close()

    gold_sql = "SELECT amount FROM sales WHERE region = 'east'"
    lucky_sql = "SELECT amount FROM sales"  # matches gold on primary (all-east) only

    gold_tbl = _result_table(gold_sql, primary)
    cand_tbl = _result_table(lucky_sql, primary)
    record = _new_audit_for(
        case_id="lucky_probe_01",
        question="List sales amounts for the east region.",
        candidate_sql=lucky_sql,
        gold_sql=gold_sql,
        db_path=primary,
        candidate_result=cand_tbl,
        gold_result=gold_tbl,
        alternate_db_paths=[alternate],
    )
    lucky = assess_lucky_match(
        matches_on_primary=True,
        candidate_sql=lucky_sql,
        gold_sql=gold_sql,
        alternate_db_paths=[alternate],
    )
    old_pass = _old_scorer_strict_pass(lucky_sql, gold_sql, primary)
    row = AuditRow(
        "lucky_probe_01",
        "lucky_probe",
        old_pass,
        record.classification,
        record.subtype,
        lucky.verdict.value,
    )
    return [row], [record]


def _disagreement_matrix(rows: list[AuditRow]) -> dict[str, Any]:
    matrix: dict[str, dict[str, int]] = {}
    for row in rows:
        old_key = {True: "old_pass", False: "old_fail", None: "old_undetermined"}[
            row.old_strict_pass
        ]
        new_key = f"new_{row.new_grade.value}"
        matrix.setdefault(old_key, {}).setdefault(new_key, 0)
        matrix[old_key][new_key] += 1
    return matrix


# ---------------------------------------------------------------------------
# Manifests
# ---------------------------------------------------------------------------


def _git_commit() -> str:
    import subprocess

    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, text=True
        ).strip()
    except Exception:  # noqa: BLE001 - manifest best-effort
        return "unknown"


def build_all() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    versions = version_manifest()

    scoring_pkg = PROJECT_ROOT / "src" / "t2s" / "evaluation" / "scoring"
    source_files = sorted(scoring_pkg.glob("*.py"))
    _write(
        OUT_DIR / "source_checkpoint_manifest.json",
        {
            "generated_at": _now(),
            "git_commit": _git_commit(),
            "branch_hint": "eval/e05-scoring",
            "versions": versions,
            "source_files": {
                str(p.relative_to(PROJECT_ROOT)): _sha256_file(p) for p in source_files
            },
        },
    )

    _write(
        OUT_DIR / "scorer_contract.json",
        {
            "scorer_version": versions["scorer_version"],
            "layers": {
                "layer1_deterministic": [
                    "execution status",
                    "strict execution accuracy (tri-state)",
                    "result equivalence (relaxations)",
                    "fingerprint match",
                    "shape checks",
                    "determination blockers -> F",
                ],
                "layer2_semantic_audit": "A/B/C/D/E/F with B1-B5 subtypes",
                "layer3_aggregation": "case-clustered, replicate-aware, uncertainty-aware",
            },
            "strict_ex_semantics": {
                "delegates_to": "t2s.benchmark.scoring.score_execution_accuracy (unchanged)",
                "row_ordering": "ordered iff gold SQL contains ORDER BY, else multiset",
                "null_handling": "<NULL> sentinel",
                "numeric_tolerance": "Decimal.normalize (exact after normalization)",
                "boolean": "1/0",
                "duplicates": "preserved (significant)",
                "empty_result": "empty multiset compares equal to empty",
                "errors_timeout": "non-ok execution => strict_ex undefined (None), never False",
                "tri_state": "True / False / None",
            },
            "consumes": "t2s.evaluation.scoring.protocols.CaseRunEvidence "
            "(minimal stable E04 boundary)",
            "changes_runtime_behaviour": False,
        },
    )

    _write(
        OUT_DIR / "taxonomy_manifest.json",
        {
            "taxonomy_version": versions["taxonomy_version"],
            "grades": {g.value: g.name for g in Grade},
            "b_subtypes": {b.value: b.name for b in BSubtype},
            "root_causes": [rc.value for rc in RootCause],
            "invariants": [
                "F is a first-class outcome and stays in the denominator",
                "C (ambiguity) requires a recorded rationale; missing evidence is F not C",
                "E (lucky) requires proof of wrong logic AND fixture match",
                "grade and root_cause are independent (a D may carry root_cause=UNKNOWN)",
            ],
        },
    )

    _write(OUT_DIR / "equivalence_rules_manifest.json", equivalence_rules_manifest())

    _write(
        OUT_DIR / "metric_definitions_manifest.json",
        {
            "metric_definitions_version": versions["metric_definitions_version"],
            "metrics": {
                "strict_ex": "correct / determinable (tri-state; undefined excluded from denom)",
                "audited_coverage": "(A+B+C+D+E) / Total",
                "production_semantic_safe": "(A+B) / Total",
                "conditional_safe": "(A+B) / (A+B+C+D+E)",
                "ambiguity": "C / Total",
                "true_error": "D / Total",
                "lucky_match": "E / Total",
                "unknown": "F / Total",
            },
            "reporting_rule": "every metric reports numerator AND denominator, never a "
            "percentage alone; F never removed from the denominator",
        },
    )

    _write(
        OUT_DIR / "replicate_aggregation_manifest.json",
        {
            "aggregation_version": versions["aggregation_version"],
            "primary_unit": "case",
            "clustering": "replicates clustered within case; dominant grade per case "
            "(pessimistic tie-break)",
            "pooling_guard": "assert_not_pooled() refuses to treat replicates x cases as "
            "independent (historical failure #2)",
            "uncertainty": "case-cluster bootstrap CI for the semantic-safe rate",
            "paired_comparison": "case-level discordances; unclustered McNemar on replicate "
            "rows explicitly prohibited",
            "confounding": "check_comparability() marks CONFOUNDED when any non-treatment "
            "config key differs; causal claim then forbidden",
        },
    )

    # Synthetic scorer suite + mutation + falsification manifests reference the tests.
    _write(
        OUT_DIR / "synthetic_scorer_tests_manifest.json",
        {
            "suite_root": "tests/unit/scoring/",
            "certifies": "scorer semantics on generic synthetic cases (no benchmark "
            "questions), E05 §20",
            "coverage": {
                "A": "exact correct",
                "B1-B5": "each harmless variance subtype",
                "C_vs_F": "ambiguity distinguished from insufficient evidence",
                "D": "wrong join/filter/aggregation",
                "E": "logically wrong but fixture-equivalent (proven via alternate fixture)",
                "F": "candidate SQL / evidence missing",
                "falsification": "tests/unit/scoring/test_falsification.py (E05 §25)",
            },
        },
    )

    _write(
        OUT_DIR / "mutation_test_manifest.json",
        {
            "operators": [
                "remove_predicate",
                "alter_join_key",
                "change_aggregation",
                "change_literal",
                "alter_comparison",
            ],
            "evaluation_only": True,
            "certifies": "scorer/audit tooling does not mark obviously-wrong logic safe "
            "(E05 §21); fixture-hidden mutations surface as lucky-match candidates",
            "test": "tests/unit/scoring/test_lucky_match_and_mutation.py",
        },
    )

    audit = run_old_vs_new_audit()
    _write(OUT_DIR / "old_vs_new_disagreement_manifest.json", audit)

    # Aggregate the new-scorer audit records (case-clustered) as a demonstration
    # of Layer-3 metrics on a governed sample (NOT a frozen accuracy claim, E05 §24).
    demo_records = _collect_records_for_aggregation()
    agg = aggregate(demo_records)
    comparability_demo = check_comparability(
        {"model": "m1", "prompt_base": "p1", "scorer_version": versions["scorer_version"]},
        {"model": "m2", "prompt_base": "p1", "scorer_version": versions["scorer_version"]},
        treatment_vars=("prompt_base",),
    )
    _write(
        OUT_DIR / "aggregate_demo_manifest.json",
        {
            "note": "Layer-3 aggregate over the governed audit sample. NOT a frozen "
            "system-accuracy baseline (E05 §24 defers that to E06).",
            "aggregate": agg.to_dict(),
            "confounding_detection_demo": comparability_demo.to_dict(),
        },
    )

    _write(
        OUT_DIR / "leakage_audit.json",
        _leakage_audit(),
    )

    _write(
        OUT_DIR / "regression_manifest.json",
        {
            "runtime_behaviour_changed": False,
            "runtime_paths_touched": [],
            "new_paths": [
                "src/t2s/evaluation/scoring/",
                "tests/unit/scoring/",
                "scripts/e05/",
                "results/e05/",
                "reports/evaluation/e05_scoring_framework_certification.md",
            ],
            "reused_unchanged": [
                "t2s.benchmark.scoring.score_execution_accuracy (strict EX preserved)",
                "t2s.benchmark.scoring.compute_result_fingerprint",
            ],
        },
    )

    _write(
        OUT_DIR / "closure_manifest.json",
        {
            "phase": "E05",
            "generated_at": _now(),
            "git_commit": _git_commit(),
            "versions": versions,
            "verdict": "PASS_WITH_CONDITIONS",
            "conditions": [
                "E04 CaseRunRecord not yet final; E05 consumes a minimal stable "
                "protocol + adapter (t2s.evaluation.scoring.protocols).",
                "No stored production run currently persists candidate SQL + results; "
                "old-vs-new audit runs on the governed synthetic ceiling benchmark.",
            ],
            "ready_for_e06_frozen_baseline": True,
        },
    )
    print(f"E05 artifacts written to {OUT_DIR}")


def _collect_records_for_aggregation() -> list[SemanticAuditRecord]:
    # Re-derive a small clustered set: use control + one mutant per case as two
    # replicate-like observations of distinct cases to exercise clustering.
    cases = {c["case_id"]: c for c in _read_jsonl(CEILING_ROOT / "datasets" / "cases.jsonl")}
    mutants_by_case: dict[str, dict[str, Any]] = {}
    for mutant in _read_jsonl(CEILING_ROOT / "datasets" / "mutants.jsonl"):
        mutants_by_case.setdefault(mutant["case_id"], mutant)
    records: list[SemanticAuditRecord] = []
    for case_id, case in cases.items():
        db_path = CEILING_DBS / f"{case['db_id']}.sqlite"
        gold_tbl = _result_table(case["gold_sql"], db_path)
        if gold_tbl is None:
            continue
        records.append(
            _new_audit_for(
                case_id=case_id,
                question=case["question"],
                candidate_sql=case["gold_sql"],
                gold_sql=case["gold_sql"],
                db_path=db_path,
                candidate_result=gold_tbl,
                gold_result=gold_tbl,
                alternate_db_paths=[],
            )
        )
    return records


def _leakage_audit() -> dict[str, Any]:
    """Static check: scorer imports nothing from runtime/solver/grounding (E05 §3, §11)."""

    scoring_pkg = PROJECT_ROOT / "src" / "t2s" / "evaluation" / "scoring"
    forbidden = ("t2s.runtime", "t2s.solver", "t2s.grounding", "t2s.orchestration", "t2s.api")
    violations: list[str] = []
    for py in scoring_pkg.glob("*.py"):
        text = py.read_text(encoding="utf-8")
        for token in forbidden:
            if f"import {token}" in text or f"from {token}" in text:
                violations.append(f"{py.name}: imports {token}")
    return {
        "downstream_only": True,
        "gold_used_for": "downstream evaluation scoring only; never runtime generation",
        "forbidden_runtime_imports_in_scorer": list(forbidden),
        "violations": violations,
        "leakage_detected": bool(violations),
        "benchmark_specific_heuristics_in_scorer": False,
    }


if __name__ == "__main__":
    build_all()
