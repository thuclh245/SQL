"""V2-P00R governance guards for experimental context/serialization profiles.

Ensures:
- The default production runtime factory does not import the experimental
  context/serialization profile modules (so they cannot become default runtime
  behaviour).
- The default ``DirectSqlPromptBuilder`` uses no custom schema serializer
  (S0 baseline via ``_format_authorized_schema``).
- The experimental modules import no benchmark case, gold SQL, or evaluation
  loader (they must remain configuration-only, not benchmark-coupled).
"""

import ast
import importlib.util
from pathlib import Path

from t2s.solver.prompt_builder import DirectSqlPromptBuilder

EXPERIMENTAL_MODULES = [
    Path("src/t2s/runtime/context_experiment_profile.py"),
    Path("src/t2s/solver/context_serializer.py"),
]

FORBIDDEN_IMPORT_PREFIXES = (
    "t2s.benchmark",
    "t2s.evaluation",
    "tests",
    "scripts",
)


def _module_imports(module_path: Path) -> list[str]:
    if not module_path.exists():
        return []
    tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
    return imports


def test_default_prompt_builder_has_no_custom_schema_serializer() -> None:
    """The default constructor keeps the S0 baseline serializer, not an experimental arm."""
    builder = DirectSqlPromptBuilder()
    assert builder.schema_serializer is None, (
        "Default DirectSqlPromptBuilder must not carry an experimental schema serializer; "
        "the S0 baseline (_format_authorized_schema) is the production default."
    )


def test_bootstrap_runtime_factory_does_not_import_experimental_profiles() -> None:
    """Production runtime assembly must not depend on the experimental profile modules."""
    factory_path = Path("src/t2s/bootstrap/runtime_factory.py")
    imports = _module_imports(factory_path)
    forbidden = {
        "t2s.runtime.context_experiment_profile",
        "t2s.solver.context_serializer",
    }
    intersecting = forbidden.intersection(imports)
    assert not intersecting, (
        "src/t2s/bootstrap/runtime_factory.py must not import experimental profile modules "
        f"({intersecting}); doing so would silently promote an experimental arm to production."
    )


def test_experimental_modules_do_not_import_benchmark_or_evaluation_code() -> None:
    """Experimental profiles must stay configuration-only, not benchmark-coupled."""
    violations: list[tuple[str, str]] = []
    for module_path in EXPERIMENTAL_MODULES:
        for imp in _module_imports(module_path):
            if any(
                imp == prefix or imp.startswith(f"{prefix}.")
                for prefix in FORBIDDEN_IMPORT_PREFIXES
            ):
                violations.append((str(module_path), imp))
    assert not violations, (
        "Experimental profile modules must not import evaluation/benchmark code: "
        f"{violations}"
    )


def test_experimental_profile_modules_are_present_but_optional() -> None:
    """If the experimental modules exist on disk, they must be importable without side effects.

    A missing module is acceptable (they are opt-in and may not be committed); if
    present they must load cleanly. This guards against a broken import from
    accidentally propagating into the evaluation runner.
    """
    for module_path in EXPERIMENTAL_MODULES:
        if not module_path.exists():
            continue
        spec = importlib.util.spec_from_file_location(module_path.stem, module_path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
