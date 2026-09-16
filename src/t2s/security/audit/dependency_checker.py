"""Direct and transitive dependency boundary checkers for production runtime."""

from __future__ import annotations

import ast
import os
from datetime import UTC, datetime
from pathlib import Path

from t2s.security.audit.contracts import AuditFinding, AuditResult, AuditStatus


class DependencyBoundaryChecker:
    """Audits direct and transitive import boundaries from production code."""

    FORBIDDEN_PREFIXES = (
        "t2s.benchmark",
        "t2s.evaluation",
        "tests",
        "scripts",
        "results",
        "reports",
    )

    DEFAULT_ENTRYPOINTS = [
        "src/t2s/bootstrap/application.py",
        "src/t2s/bootstrap/runtime_factory.py",
        "src/t2s/runtime/text_to_sql_runtime.py",
        "src/t2s/api/query_routes.py",
    ]

    def __init__(self, root_dir: Path | str = "src/t2s") -> None:
        self.root_dir = Path(root_dir)

    def _get_production_files(self) -> list[Path]:
        excluded = {"src/t2s/benchmark", "src/t2s/evaluation"}
        py_files = []
        for root, _, files in os.walk(self.root_dir):
            rel = Path(root).as_posix()
            if any(rel == exc or rel.startswith(f"{exc}/") for exc in excluded):
                continue
            for f in files:
                if f.endswith(".py"):
                    py_files.append(Path(root) / f)
        return sorted(py_files)

    @staticmethod
    def _extract_imports(file_path: Path) -> set[str]:
        tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for n in node.names:
                    imports.add(n.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.add(node.module)
        return imports

    @staticmethod
    def _module_to_path(mod_name: str) -> str | None:
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

    def check_direct_dependencies(self) -> AuditResult:
        files = self._get_production_files()
        findings: list[AuditFinding] = []

        for f in files:
            try:
                imports = self._extract_imports(f)
            except Exception as exc:
                findings.append(
                    AuditFinding(
                        finding_id=f"PARSE-DEP-{len(findings) + 1:03d}",
                        category="SYNTAX_ERROR",
                        location=str(f),
                        description=f"Failed to parse file for import analysis: {exc}",
                        evidence=str(exc),
                        severity="CRITICAL",
                    )
                )
                continue

            for imp in imports:
                if any(imp == p or imp.startswith(f"{p}.") for p in self.FORBIDDEN_PREFIXES):
                    findings.append(
                        AuditFinding(
                            finding_id=f"DIRECT-DEP-{len(findings) + 1:03d}",
                            category="ILLEGAL_DIRECT_DEPENDENCY",
                            location=str(f),
                            description=(
                                f"Direct import of forbidden research/benchmark module '{imp}'"
                            ),
                            evidence=imp,
                            severity="CRITICAL",
                        )
                    )

        status = AuditStatus.PASS if len(findings) == 0 else AuditStatus.FAIL
        return AuditResult(
            check_name="direct_dependency_audit",
            status=status,
            timestamp=datetime.now(UTC).isoformat(),
            tool_or_function="DependencyBoundaryChecker.check_direct_dependencies",
            scope="src/t2s production modules",
            checked_count=len(files),
            violation_count=len(findings),
            violations=findings,
            evidence_paths=["src/t2s"],
            limitations=[],
            details={
                "scanned_files": len(files),
                "forbidden_prefixes": list(self.FORBIDDEN_PREFIXES),
            },
        )

    def check_transitive_dependencies(self, entrypoints: list[str] | None = None) -> AuditResult:
        active_entrypoints = entrypoints or self.DEFAULT_ENTRYPOINTS
        visited: set[str] = set()
        graph: dict[str, list[str]] = {}
        queue = list(active_entrypoints)
        findings: list[AuditFinding] = []

        while queue:
            curr = queue.pop(0)
            if curr in visited:
                continue
            visited.add(curr)

            curr_path = Path(curr)
            if not curr_path.is_file():
                continue

            try:
                imps = self._extract_imports(curr_path)
            except Exception as exc:
                findings.append(
                    AuditFinding(
                        finding_id=f"TRANS-PARSE-{len(findings) + 1:03d}",
                        category="SYNTAX_ERROR",
                        location=curr,
                        description=f"Failed to parse entrypoint module: {exc}",
                        evidence=str(exc),
                        severity="CRITICAL",
                    )
                )
                continue

            graph[curr] = sorted(imps)
            for imp in imps:
                p = self._module_to_path(imp)
                if p and p not in visited:
                    queue.append(p)

        # Check all reachable modules for forbidden imports
        for m in sorted(visited):
            for imp in graph.get(m, []):
                if any(imp == p or imp.startswith(f"{p}.") for p in self.FORBIDDEN_PREFIXES):
                    findings.append(
                        AuditFinding(
                            finding_id=f"TRANS-DEP-{len(findings) + 1:03d}",
                            category="ILLEGAL_TRANSITIVE_DEPENDENCY",
                            location=m,
                            description=(
                                f"Module reachable from entrypoints imports forbidden '{imp}'"
                            ),
                            evidence=f"{m} -> {imp}",
                            severity="CRITICAL",
                        )
                    )

        status = AuditStatus.PASS if len(findings) == 0 else AuditStatus.FAIL
        return AuditResult(
            check_name="transitive_dependency_audit",
            status=status,
            timestamp=datetime.now(UTC).isoformat(),
            tool_or_function="DependencyBoundaryChecker.check_transitive_dependencies",
            scope="Reachable modules from production entrypoints",
            checked_count=len(visited),
            violation_count=len(findings),
            violations=findings,
            evidence_paths=active_entrypoints,
            limitations=[],
            details={
                "entrypoints": active_entrypoints,
                "reachable_modules_count": len(visited),
                "reachable_modules": sorted(visited),
                "dependency_graph": graph,
            },
        )


def audit_direct_dependencies(root_dir: Path | str = "src/t2s") -> AuditResult:
    """Convenience top-level wrapper to audit direct dependencies."""
    return DependencyBoundaryChecker(root_dir=root_dir).check_direct_dependencies()


def audit_transitive_dependencies(
    root_dir: Path | str = "src/t2s", entrypoints: list[str] | None = None
) -> AuditResult:
    """Convenience top-level wrapper to audit transitive dependencies."""
    return DependencyBoundaryChecker(root_dir=root_dir).check_transitive_dependencies(
        entrypoints=entrypoints
    )
