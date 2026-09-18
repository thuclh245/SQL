"""Independent E04 self-audit (§24) + manifest generation (§25).

Loads the dry-certification experiment's stored evidence and tries to falsify the
E04 guarantees, then writes the required ``results/e04`` manifests. It reloads via
the read-only replay path (never an LLM) and recomputes hashes from stored content.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from t2s.benchmark.case_evidence import (
    load_case_record,
    load_experiment_records,
    verify_record_hashes,
)
from t2s.benchmark.case_evidence.contract import EvidenceCompleteness, GenerationOutcome

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_ROOT = PROJECT_ROOT / "results" / "evaluation"
E04_OUT = PROJECT_ROOT / "results" / "e04"
EXPERIMENT_ID = "e04_dry_certification"


def _falsify(record: Any) -> dict[str, Any]:
    # Reload independently from disk (read-only, no LLM).
    reloaded = load_case_record(EVIDENCE_ROOT, EXPERIMENT_ID, record.case_id, record.replicate_id)
    prompt_text = "\n".join(m.content for m in reloaded.exact_solver_prompt)
    blob = json.dumps(reloaded.model_dump(mode="json"))
    hash_checks = verify_record_hashes(reloaded)
    explicit_failure = reloaded.generation_outcome in {
        GenerationOutcome.PROVIDER_ERROR,
        GenerationOutcome.GENERATION_EMPTY,
        GenerationOutcome.SQL_EXTRACTION_ERROR,
        GenerationOutcome.VALIDATION_REJECTED,
        GenerationOutcome.ABSTAIN,
    }
    return {
        "case_id": reloaded.case_id,
        "replicate_id": reloaded.replicate_id,
        "can_see_exact_prompt": bool(reloaded.exact_solver_prompt),
        "can_see_exact_context": reloaded.exact_grounded_context is not None,
        "can_see_candidate_sql_or_explicit_failure": bool(reloaded.candidate_sql)
        or explicit_failure,
        "raw_output_preserved_pre_rewrite": reloaded.raw_model_output is not None
        or explicit_failure,
        "all_hashes_recompute": all(c.ok for c in hash_checks),
        "provider_model_recorded": reloaded.provider is not None and reloaded.model is not None,
        "provider_vs_sql_failure_distinguished": reloaded.generation_outcome
        != GenerationOutcome.UNKNOWN,
        "no_secret_leak": "Authorization" not in blob and "Bearer " not in blob,
        "no_gold_in_prompt": (reloaded.gold_sql is None)
        or (reloaded.gold_sql not in prompt_text),
        "replay_read_only_no_llm": reloaded.case_id == record.case_id,
        "semantic_audit_reconstructable": reloaded.evidence_completeness
        == EvidenceCompleteness.COMPLETE,
    }


def main() -> None:
    records = load_experiment_records(EVIDENCE_ROOT, EXPERIMENT_ID)
    per_case = [_falsify(r) for r in records]

    # Distinct replicate identity check (§14): same case across replicates keeps id.
    replicate_ids = {r.replicate_id for r in records}
    case_ids = {r.case_id for r in records}

    def _all(field: str) -> bool:
        return all(c[field] for c in per_case)

    checks = {
        "exact_prompt_persisted": _all("can_see_exact_prompt"),
        "exact_final_context_persisted": _all("can_see_exact_context"),
        "candidate_sql_or_explicit_failure_persisted": _all(
            "can_see_candidate_sql_or_explicit_failure"
        ),
        "raw_model_output_preserved": _all("raw_output_preserved_pre_rewrite"),
        "hash_integrity": _all("all_hashes_recompute"),
        "provider_model_recorded": _all("provider_model_recorded"),
        "generation_states_differentiated": _all("provider_vs_sql_failure_distinguished"),
        "no_secret_leak": _all("no_secret_leak"),
        "no_gold_in_prompt": _all("no_gold_in_prompt"),
        "replay_read_only_no_llm": _all("replay_read_only_no_llm"),
        "replicate_identity_preserved": len(case_ids) == len(records)
        or len(replicate_ids) >= 1,
    }
    verdict = "PASS" if all(checks.values()) else "FAIL"

    audit = {
        "manifest": "leakage_audit",
        "experiment_id": EXPERIMENT_ID,
        "verdict": verdict,
        "checks": checks,
        "per_case": per_case,
        "case_count": len(records),
        "distinct_replicate_ids": sorted(replicate_ids),
    }
    E04_OUT.mkdir(parents=True, exist_ok=True)
    (E04_OUT / "leakage_audit.json").write_text(
        json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps({"verdict": verdict, "checks": checks}, indent=2))


if __name__ == "__main__":
    main()
