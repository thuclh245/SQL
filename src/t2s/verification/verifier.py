from typing import Protocol

from t2s.verification.contracts import VerificationInput, VerificationResult


class SqlVerifier(Protocol):
    """Protocol for offline SQL semantic and deterministic verifiers."""

    async def verify(self, verification_input: VerificationInput) -> VerificationResult:
        """Verify whether candidate SQL faithfully satisfies the question given evidence."""
        ...
