import re
from typing import Any

SECRET_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"sk-proj-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"sk-or-v1-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"sk-[A-Za-z0-9_\-]{24,}"),
]


def contains_secret(text: str) -> bool:
    """Check whether a string contains known secret patterns."""
    if not isinstance(text, str):
        return False
    for pattern in SECRET_PATTERNS:
        if pattern.search(text):
            return True
    return False


def sanitize_text(text: str, replacement: str = "[REDACTED_SECRET]") -> str:
    """Sanitize secrets in a text string."""
    if not isinstance(text, str):
        return text

    sanitized = text
    sanitized = re.sub(r"sk-proj-[A-Za-z0-9_\-]+", replacement, sanitized)
    sanitized = re.sub(r"sk-or-v1-[A-Za-z0-9_\-]+", replacement, sanitized)
    sanitized = re.sub(r"sk-[A-Za-z0-9_\-]{24,}", replacement, sanitized)
    return sanitized


def sanitize_data(data: Any, replacement: str = "[REDACTED_SECRET]") -> Any:
    """Recursively sanitize data structures (dict, list, str)."""
    if isinstance(data, str):
        return sanitize_text(data, replacement=replacement)
    if isinstance(data, dict):
        return {k: sanitize_data(v, replacement=replacement) for k, v in data.items()}
    if isinstance(data, list):
        return [sanitize_data(v, replacement=replacement) for v in data]
    return data
