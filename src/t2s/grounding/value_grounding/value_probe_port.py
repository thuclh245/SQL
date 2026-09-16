"""Capability boundary for reading candidate literals out of a live database.

Kept separate from ``QueryExecutorPort`` on purpose: that port executes
model-authored SQL and is guarded by AST parsing, safety and access validation.
Value probes are system-authored, parameterized statements over catalog-supplied
identifiers, so they take a narrower contract that cannot express arbitrary SQL.
"""

from typing import Protocol

from t2s.grounding.value_grounding.value_grounding_contracts import (
    ValueProbeOutcome,
    ValueProbeRequest,
)


class ValueProbePort(Protocol):
    """Reads a bounded set of distinct literals from one authorized column."""

    def probe_matching_values(self, probe_request: ValueProbeRequest) -> ValueProbeOutcome:
        """Return literals in the column equal to any supplied normalized term.

        Implementations must bind terms as parameters, run read-only, and apply
        the request's row and time bounds.
        """
        ...

    def probe_column_domain(self, probe_request: ValueProbeRequest) -> ValueProbeOutcome:
        """Return up to ``max_values`` distinct literals to test for an enum-like domain.

        Implementations must fetch at most ``max_values + 1`` rows and set
        ``domain_truncated`` when that extra row appears, so a high-cardinality
        column is detectable without scanning its full domain.
        """
        ...
