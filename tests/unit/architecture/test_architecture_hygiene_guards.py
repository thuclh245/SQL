"""Comprehensive Architectural CI Hygiene and Contamination Guards (Guards 1-10).

Enforces:
1. Production naming (zero phase/experiment names)
2. Benchmark naming (zero benchmark tokens in runtime)
3. Direct dependency boundaries
4. Transitive runtime dependency boundaries
5. Gold field isolation
6. Prompt hygiene
7. Secret scanning across tracked files
8. Case ID prohibition in production
9. Historical artifact runtime isolation
10. Production filename/path phase-neutrality
"""

import ast
import os
import re
import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

from t2s.verification.sql_semantic_risk_validator import ValidationInput


def _get_production_python_files() -> list[Path]:
    prod_root = Path("src/t2s")
    excluded = {"src/t2s/benchmark", "src/t2s/evaluation", "src/t2s/security/audit"}
    py_files = []
    for root, _, files in os.walk(prod_root):
        rel_root = Path(root).as_posix()
        if any(rel_root == exc or rel_root.startswith(f"{exc}/") for exc in excluded):
            continue
        for f in files:
            if f.endswith(".py"):
                py_files.append(Path(root) / f)
    return py_files


# Guard 1: Production Naming
def test_guard_1_production_naming() -> None:
    """Production code must contain ZERO phase names or experiment identifiers."""
    phase_pattern = re.compile(
        r"\b(p[0-9]|e[0-9]|p8e[0-9]+|phase[0-9]+|phase_[0-9]+)\b", re.IGNORECASE
    )
    violations = []

    for file_path in _get_production_python_files():
        lines = file_path.read_text(encoding="utf-8").splitlines()
        for idx, line in enumerate(lines, 1):
            stripped = line.strip()
            m_phase = phase_pattern.search(stripped)
            if m_phase:
                violations.append(
                    (str(file_path), idx, f"Phase name '{m_phase.group(0)}' in line: {stripped}")
                )

    assert not violations, "Guard 1: Production naming violations found:\n" + "\n".join(
        str(v) for v in violations
    )


# Guard 2: Benchmark Naming
def test_guard_2_benchmark_naming() -> None:
    """Production code must contain ZERO benchmark dataset identifiers."""
    benchmark_pattern = re.compile(
        r"\b(bird|dev100|mini_dev|spider|pilot_v1|eval_v1)\b", re.IGNORECASE
    )
    violations = []

    for file_path in _get_production_python_files():
        lines = file_path.read_text(encoding="utf-8").splitlines()
        for idx, line in enumerate(lines, 1):
            stripped = line.strip()
            m_bench = benchmark_pattern.search(stripped)
            if m_bench:
                violations.append(
                    (
                        str(file_path),
                        idx,
                        f"Benchmark name '{m_bench.group(0)}' in line: {stripped}",
                    )
                )

    assert not violations, "Guard 2: Benchmark naming violations found:\n" + "\n".join(
        str(v) for v in violations
    )


# Guard 3: Direct Dependency Boundary
def test_guard_3_direct_dependency_boundary() -> None:
    """Production modules must never import evaluation, benchmark, test, or experiment code."""
    forbidden_prefixes = (
        "t2s.benchmark",
        "t2s.evaluation",
        "tests",
        "scripts",
        "results",
        "reports",
    )
    violations = []

    for file_path in _get_production_python_files():
        tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if any(
                        alias.name == p or alias.name.startswith(f"{p}.")
                        for p in forbidden_prefixes
                    ):
                        violations.append((str(file_path), node.lineno, alias.name))
            elif isinstance(node, ast.ImportFrom):
                if node.module and any(
                    node.module == p or node.module.startswith(f"{p}.") for p in forbidden_prefixes
                ):
                    violations.append((str(file_path), node.lineno, node.module))

    assert not violations, f"Guard 3: Forbidden direct dependency violations found: {violations}"


# Guard 4: Transitive Runtime Dependency
def test_guard_4_transitive_runtime_dependency() -> None:
    """Modules reachable from entrypoints must be free of research/evaluation imports."""

    def get_imports(filepath: str) -> set[str]:
        tree = ast.parse(Path(filepath).read_text(encoding="utf-8"), filename=filepath)
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for n in node.names:
                    imports.add(n.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.add(node.module)
        return imports

    def module_to_path(mod_name: str) -> str | None:
        if not mod_name.startswith("t2s."):
            return None
        rel = mod_name.replace(".", "/") + ".py"
        p = Path("src") / rel
        if p.is_file():
            return str(p)
        init_p = Path("src") / mod_name.replace(".", "/") / "__init__.py"
        if init_p.is_file():
            return str(init_p)
        return None

    entrypoints = [
        "src/t2s/bootstrap/application.py",
        "src/t2s/bootstrap/runtime_factory.py",
        "src/t2s/runtime/text_to_sql_runtime.py",
        "src/t2s/api/query_routes.py",
    ]

    visited = set()
    graph = {}
    queue = list(entrypoints)

    while queue:
        curr = queue.pop(0)
        if curr in visited:
            continue
        visited.add(curr)
        imps = get_imports(curr)
        graph[curr] = list(imps)
        for imp in imps:
            p = module_to_path(imp)
            if p and p not in visited:
                queue.append(p)

    forbidden_prefixes = (
        "t2s.benchmark",
        "t2s.evaluation",
        "tests",
        "scripts",
        "results",
        "reports",
    )
    violations = []
    for m in visited:
        for imp in graph.get(m, []):
            if any(imp == bad or imp.startswith(f"{bad}.") for bad in forbidden_prefixes):
                violations.append((m, imp))

    assert not violations, f"Guard 4: Transitive dependency violations found: {violations}"


# Guard 5: Gold Field Isolation
def test_guard_5_gold_field_isolation() -> None:
    """Production DTOs must strictly reject gold data fields."""
    forbidden_fields = [
        "gold_sql",
        "gold_answer",
        "gold_tables",
        "gold_columns",
        "expected_sql",
        "expected_result",
        "reference_sql",
        "ground_truth",
        "execution_score",
        "correctness",
    ]
    for forbidden_field in forbidden_fields:
        payload = {
            "question": "What is the total revenue?",
            "candidate_sql": "SELECT SUM(amount) FROM payments",
            forbidden_field: "leak",
        }
        with pytest.raises(ValidationError):
            ValidationInput.model_validate(payload)


# Guard 6: Prompt Hygiene
def test_guard_6_prompt_hygiene() -> None:
    """Production prompts must never contain few-shot examples or benchmark references."""
    prompt_root = Path("prompts")
    forbidden = [
        "bird",
        "spider",
        "student_club",
        "european_football",
        "card_games",
        "formula_1",
        "dev100",
    ]
    for p in prompt_root.rglob("*.md"):
        content = p.read_text(encoding="utf-8").lower()
        for term in forbidden:
            assert term not in content, (
                f"Guard 6: Prompt {p} contains forbidden benchmark reference: {term}"
            )


# Guard 7: Secret Scanning
def test_guard_7_secret_scanning() -> None:
    """Tracked files must not contain unmasked API keys or secrets."""
    result = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=True)
    tracked_files = result.stdout.splitlines()
    secret_pattern = re.compile(r"sk-[a-zA-Z0-9_-]{24,}")

    violations = []
    for file_str in tracked_files:
        p = Path(file_str)
        if not p.is_file():
            continue
        if (
            "test_secret_sanitization.py" in file_str
            or "test_architecture_hygiene_guards.py" in file_str
        ):
            continue
        try:
            content = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for idx, line in enumerate(content.splitlines(), 1):
            m = secret_pattern.search(line)
            if m:
                masked = m.group(0)[:6] + "..." + m.group(0)[-4:]
                violations.append((file_str, idx, masked))

    assert not violations, (
        f"Guard 7: Live secret tokens detected in git tracked files: {violations}"
    )


# Guard 8: Case ID Prohibition
def test_guard_8_case_id_prohibition() -> None:
    """Production runtime must not contain hardcoded benchmark case IDs."""
    case_pattern = re.compile(r"\b(case_\d+|dev_\d+|bird_\d+|eval_\d+)\b", re.IGNORECASE)
    violations = []

    for file_path in _get_production_python_files():
        lines = file_path.read_text(encoding="utf-8").splitlines()
        for idx, line in enumerate(lines, 1):
            m = case_pattern.search(line)
            if m:
                violations.append((str(file_path), idx, m.group(0)))

    assert not violations, (
        f"Guard 8: Hardcoded benchmark case IDs found in production: {violations}"
    )


# Guard 9: Historical Artifact Runtime Access
def test_guard_9_historical_artifact_runtime_access() -> None:
    """Runtime code must not reference results/, reports/, or benchmarks/ paths."""
    forbidden_path_literals = [
        '"results/',
        "'results/",
        '"reports/',
        "'reports/",
        '"benchmarks/',
        "'benchmarks/",
    ]
    violations = []

    for file_path in _get_production_python_files():
        content = file_path.read_text(encoding="utf-8")
        for lit in forbidden_path_literals:
            if lit in content:
                violations.append((str(file_path), lit))

    assert not violations, (
        f"Guard 9: Production code references historical research paths: {violations}"
    )


# Guard 10: Production Path Naming
def test_guard_10_production_path_naming() -> None:
    """No production file or directory under src/t2s may contain phase numbering."""
    prod_root = Path("src/t2s")
    phase_pattern = re.compile(r"\b(p[0-9]|e[0-9]|p8e[0-9]+|phase[0-9]+)\b", re.IGNORECASE)
    violations = []

    for root, dirs, files in os.walk(prod_root):
        rel_root = Path(root).as_posix()
        if "benchmark" in rel_root or "evaluation" in rel_root:
            continue
        for d in dirs:
            if phase_pattern.search(d):
                violations.append(os.path.join(root, d))
        for f in files:
            if phase_pattern.search(f):
                violations.append(os.path.join(root, f))

    assert not violations, f"Guard 10: Production paths contain phase numbering: {violations}"
