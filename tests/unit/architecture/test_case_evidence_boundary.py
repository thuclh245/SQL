"""Architecture guards for the E04 case-evidence boundary (§3, §20 item 15).

* Production runtime code must never import the evidence harness — evidence
  capture lives only in the evaluation (``benchmark``) layer.
* The evidence harness must not depend on E05's scorer implementation
  (``t2s.evaluation.scoring``): the shared interface is structural and versioned, not an
  import-time coupling. E04 also stays out of the gold-reading path
  (``t2s.benchmark.scoring`` gold execution) — the evidence layer is handed
  fingerprints, it never reads gold itself.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

CASE_EVIDENCE_ROOT = Path("src/t2s/benchmark/case_evidence")


def _imports(file_path: Path) -> list[str]:
    tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def _production_python_files() -> list[Path]:
    prod_root = Path("src/t2s")
    excluded = {"src/t2s/benchmark", "src/t2s/evaluation", "src/t2s/scoring"}
    files: list[Path] = []
    for root, _, names in os.walk(prod_root):
        rel_root = Path(root).as_posix()
        if any(rel_root == exc or rel_root.startswith(f"{exc}/") for exc in excluded):
            continue
        files.extend(Path(root) / n for n in names if n.endswith(".py"))
    return files


def test_production_runtime_does_not_import_case_evidence() -> None:
    violations: list[tuple[str, str]] = []
    for file_path in _production_python_files():
        for module in _imports(file_path):
            if module == "t2s.benchmark.case_evidence" or module.startswith(
                "t2s.benchmark.case_evidence."
            ):
                violations.append((str(file_path), module))
    assert not violations, (
        "Production runtime must not import the evidence harness: " + str(violations)
    )


def test_case_evidence_does_not_import_scorer_or_gold() -> None:
    forbidden = ("t2s.evaluation.scoring", "t2s.scoring", "t2s.benchmark.scoring")
    violations: list[tuple[str, str]] = []
    for file_path in CASE_EVIDENCE_ROOT.glob("*.py"):
        for module in _imports(file_path):
            if any(module == f or module.startswith(f"{f}.") for f in forbidden):
                violations.append((str(file_path), module))
    assert not violations, (
        "Evidence harness must stay independent of the scorer/gold boundary "
        "(shared interface is structural, versioned): " + str(violations)
    )
