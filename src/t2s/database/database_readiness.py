"""Detects an execution database that cannot answer anything.

A schema-only database — correct catalog, zero rows — is indistinguishable from a
healthy one at every layer except the answer: grounding succeeds, generation
succeeds, validation succeeds, and execution returns NULL. That NULL then reads
as a finding rather than as a misconfiguration.

The check is deliberately weak. It asserts only that the execution database holds
*some* user relation with *some* row. An individual empty table is normal in
production and is never treated as a fault; a database where every relation is
empty is not a database anyone meant to query.
"""

from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, Field


class DatabaseReadinessStatus(StrEnum):
    """Verdict on whether an execution database can serve queries."""

    READY = "ready"
    UNREACHABLE = "unreachable"
    NO_USER_RELATIONS = "no_user_relations"
    NO_DATA_ROWS = "no_data_rows"


class DatabaseReadinessReport(BaseModel):
    """Outcome of one readiness inspection.

    Row counts are capped rather than exact: the check must stay cheap enough to
    run at startup against a production database.
    """

    status: DatabaseReadinessStatus
    relation_count: int = Field(default=0, ge=0)
    inspected_relation_count: int = Field(default=0, ge=0)
    non_empty_relation_count: int = Field(default=0, ge=0)
    detail: str | None = None

    @property
    def is_ready(self) -> bool:
        return self.status == DatabaseReadinessStatus.READY


class DatabaseReadinessInspectorPort(Protocol):
    """Introspects an execution database for signs that it holds queryable data."""

    def inspect_readiness(self, max_relations_to_sample: int) -> DatabaseReadinessReport:
        """Return a readiness verdict, sampling at most the given number of relations."""
        ...
