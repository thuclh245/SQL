"""Verified context for enterprise Text-to-SQL.

The package turns three kinds of knowledge that public Text-to-SQL benchmarks hand
to the model as "evidence" into components that are built, verified and applied:

* a data profile measured from the warehouse (types, real values, ranges, grain),
* a registry of implicit data conventions mined from production queries,
  each backed by an AST check,
* gates that decline (abstain / clarify) instead of returning a plausible
  but wrong answer.

Every stage can be switched off through :class:`PipelineConfig` so that the
contribution of each one can be measured in an ablation.
"""

from t2s.verified_context.pipeline import PipelineConfig, PipelineResult, VerifiedContextPipeline

__all__ = ["PipelineConfig", "PipelineResult", "VerifiedContextPipeline"]
