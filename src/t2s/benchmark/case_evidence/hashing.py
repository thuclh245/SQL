"""Deterministic content hashing for case-run evidence (E04 §18).

All evidence hashes are SHA-256 over a canonical serialization so that a stored
hash can be recomputed byte-for-byte from stored content. A mismatch between a
stored hash and a recomputed hash means evidence corruption.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

#: Namespace tag recorded alongside hashes so the algorithm is self-describing.
HASH_ALGORITHM = "sha256"


def canonical_json(value: Any) -> str:
    """Canonical JSON used as hash input.

    Keys are sorted, separators are compact, and non-ASCII is preserved so the
    exact bytes the model received survive round-tripping.
    """

    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def sha256_text(text: str) -> str:
    """SHA-256 of a UTF-8 string (used for prompts-as-text, context, SQL)."""

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_json(value: Any) -> str:
    """SHA-256 of the canonical JSON of a JSON-serializable value."""

    return sha256_text(canonical_json(value))
