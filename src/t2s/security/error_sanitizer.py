"""Error message secret sanitizer.

Prevents credentials, passwords, and sensitive tokens from leaking through
exception messages, sync results, and quarantine records.
"""

import re

# Mask database connection URIs (e.g. postgresql://user:password@host:5432/db)
_URI_PASSWORD_PATTERN = re.compile(
    r"(postgres(?:ql)?://[^:\s]+):([^@\s]+)@",
    re.IGNORECASE,
)

# Mask generic key/token/password assignments in error texts
_GENERIC_SECRET_PATTERN = re.compile(
    r"""(?P<prefix>\b(?:password|passwd|secret|api[_-]?key|token|auth)\b\s*[:=]\s*['"]?)(?P<secret>[^\s'"]{4,})""",
    re.IGNORECASE,
)

# Mask Bearer tokens
_BEARER_PATTERN = re.compile(
    r"\b(Bearer\s+)[A-Za-z0-9_\-\.]{12,}",
    re.IGNORECASE,
)


def sanitize_error_message(text: str) -> str:
    """Scrub sensitive credentials, passwords, and API keys from error text."""
    if not text:
        return ""

    # Mask URI passwords
    sanitized = _URI_PASSWORD_PATTERN.sub(r"\1:***@", text)

    # Mask Bearer tokens
    sanitized = _BEARER_PATTERN.sub(r"\1***", sanitized)

    # Mask explicit password/secret assignments
    sanitized = _GENERIC_SECRET_PATTERN.sub(r"\g<prefix>***", sanitized)

    return sanitized
