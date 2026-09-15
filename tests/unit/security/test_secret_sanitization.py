from pathlib import Path

from t2s.security.sanitization import contains_secret, sanitize_data, sanitize_text


def test_contains_secret_detection() -> None:
    assert contains_secret("Here is my key: sk-proj-1234567890abcdef1234567890")
    assert contains_secret("Bearer sk-or-v1-abcdef1234567890abcdef12345678901234")
    assert not contains_secret("This is a normal query: SELECT * FROM customers;")
    assert not contains_secret("model = openai/gpt-oss-120b")


def test_sanitize_text_redacts_tokens() -> None:
    raw = (
        "Key 1: sk-proj-abcdef1234567890abcdef1234 and "
        "Key 2: sk-or-v1-0987654321fedcba0987654321fedcba"
    )
    sanitized = sanitize_text(raw)
    assert "sk-proj-" not in sanitized

    assert "sk-or-v1-" not in sanitized
    assert sanitized == "Key 1: [REDACTED_SECRET] and Key 2: [REDACTED_SECRET]"


def test_sanitize_data_nested_structures() -> None:
    payload = {
        "model": "gpt-oss-120b",
        "api_key": "sk-proj-supersecretkey123456789012345",
        "headers": ["Authorization", "Bearer sk-or-v1-tokenhere1234567890abcdef"],
        "safe_int": 42,
    }
    sanitized = sanitize_data(payload)
    assert sanitized["api_key"] == "[REDACTED_SECRET]"
    assert sanitized["headers"] == ["Authorization", "Bearer [REDACTED_SECRET]"]
    assert sanitized["safe_int"] == 42


def test_no_secrets_in_reports_and_src() -> None:
    root = Path(__file__).resolve().parents[3]
    scan_dirs = [
        root / "reports",
        root / "src",
        root / "benchmarks",
        root / "configs",
        root / "results",
    ]

    for scan_dir in scan_dirs:
        if not scan_dir.exists():
            continue
        for path in scan_dir.rglob("*"):
            if path.is_file() and path.suffix in {".py", ".md", ".json", ".jsonl"}:
                text = path.read_text(encoding="utf-8", errors="ignore")
                assert not contains_secret(text), f"Found potential secret in {path}"
