"""Explicit cost bounds for value grounding.

Every limit that shapes database load is named here rather than hidden as a
literal at a call site, so the per-request probe ceiling stays auditable:
at most ``max_value_columns * 2`` probes, and never more.
"""

from pydantic import BaseModel, Field


class ValueGroundingBudget(BaseModel):
    """Bounds on candidate columns, probes, terms and returned literals."""

    max_value_columns: int = Field(default=6, gt=0)
    max_value_candidates_per_column: int = Field(default=5, gt=0)
    max_question_terms: int = Field(default=32, gt=0)
    max_term_length: int = Field(default=64, gt=0)
    min_term_length: int = Field(default=2, gt=0)
    value_lookup_timeout_ms: int = Field(default=1500, gt=0)
    enumerate_low_cardinality_domains: bool = Field(default=True)
    max_enumerated_domain_values: int = Field(default=12, gt=0)
    max_bindings: int = Field(default=24, gt=0)

    @property
    def max_probes_per_request(self) -> int:
        """Hard ceiling on database round trips for one request."""
        probes_per_column = 2 if self.enumerate_low_cardinality_domains else 1
        return self.max_value_columns * probes_per_column
