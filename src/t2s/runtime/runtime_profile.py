"""Reusable semantic runtime profile shared by API and benchmark entrypoints."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from t2s.grounding import GroundingBudget
from t2s.orchestration import EscalationBudget
from t2s.runtime.runtime_contracts import ValidatorMode

PlannerMode = Literal["off", "deterministic", "llm"]
EvidenceMode = Literal["none", "inline", "structured"]


class SemanticRuntimeProfile(BaseModel):
    """The semantic configuration of a constructed Text-to-SQL runtime.

    It deliberately excludes transport, database connection details, identities,
    credentials, artifact writers, and gold scoring. Those are entrypoint concerns,
    not semantic runtime behavior.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider_identifier: str = "openai_compatible"
    model_name: str = "gpt-oss-120b"
    temperature: float = 0.0
    request_timeout_seconds: float = Field(default=120.0, gt=0)
    retry_policy: Literal["none"] = "none"
    seed_policy: Literal["not_sent"] = "not_sent"
    prompt_version: str = "v001"
    evidence_mode: EvidenceMode = "none"
    grounding_budget: GroundingBudget = Field(default_factory=GroundingBudget)
    value_linking_enabled: bool = False
    planner_mode: PlannerMode = "off"
    result_verifier_enabled: bool = True
    validator_mode: ValidatorMode = ValidatorMode.SHADOW
    release_candidates_with_caveats: bool = True
    escalation_budget: EscalationBudget = Field(default_factory=EscalationBudget)
