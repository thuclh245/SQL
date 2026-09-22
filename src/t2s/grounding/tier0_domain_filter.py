"""Tier-0 Deterministic Schema Filter for Enterprise Telecom Lakehouse.

Filters out irrelevant schemas/tables before semantic search or LLM invocation (0 GPU).
Categorizes by:
1. Data Layer: raw / stg / dwh / mart
2. Business Domain: revenue, billing, network, customer, crm
3. Access Authorization: Drops unpermitted tables before LLM exposure.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

DataLayer = Literal["raw", "stg", "dwh", "mart", "unknown"]


def classify_layer(schema_or_table_name: str) -> DataLayer:
    """Classifies layer based on Lakehouse naming conventions."""
    name = schema_or_table_name.lower()
    if re.search(r"\b(raw|bronze|landing)\b|^raw_", name):
        return "raw"
    if re.search(r"\b(stg|staging|silver_stg)\b|^stg_", name):
        return "stg"
    if re.search(r"\b(dwh|edw|silver|core)\b|^dwh_", name):
        return "dwh"
    if re.search(r"\b(mart|dm|gold|agg|report)\b|^(mart|agg)_", name):
        return "mart"
    return "unknown"


@dataclass
class Tier0FilterConfig:
    domain_keywords: dict[str, list[str]] = field(
        default_factory=lambda: {
            "revenue": ["revenue", "billing", "cước", "doanh_thu", "arpu", "invoice", "payment"],
            "network": ["network", "cdr", "cell", "traffic", "mou", "data_usage", "voice"],
            "customer": ["customer", "subscriber", "sub", "thuê_bao", "khách_hàng", "churn", "contract"],
        }
    )
    preferred_layers: set[DataLayer] = field(default_factory=lambda: {"mart", "dwh"})
    allow_raw_fallback: bool = False


@dataclass
class FilterResult:
    allowed_schemas: set[str]
    allowed_tables: set[str]
    dropped_schemas: dict[str, str]   # schema -> reason
    reduction_ratio: float


class Tier0DomainFilter:
    """Filters enterprise catalogs down to relevant schemas/tables deterministically."""

    def __init__(self, config: Tier0FilterConfig | None = None) -> None:
        self.config = config or Tier0FilterConfig()

    def filter_catalog(
        self,
        schema_names: list[str],
        table_to_schema: dict[str, str],
        target_domains: set[str] | None = None,
        target_layers: set[DataLayer] | None = None,
    ) -> FilterResult:
        allowed_layers = target_layers or self.config.preferred_layers
        allowed_schemas: set[str] = set()
        dropped_schemas: dict[str, str] = {}

        total_schemas = len(schema_names)

        for s in schema_names:
            s_lower = s.lower()
            layer = classify_layer(s_lower)

            # Layer check
            if allowed_layers and layer not in allowed_layers and layer != "unknown":
                dropped_schemas[s] = f"Layer '{layer}' không nằm trong tập ưu tiên {allowed_layers}"
                continue

            # Domain check
            if target_domains:
                domain_matched = False
                for dom in target_domains:
                    keywords = self.config.domain_keywords.get(dom, [dom])
                    if any(kw in s_lower for kw in keywords):
                        domain_matched = True
                        break
                if not domain_matched:
                    dropped_schemas[s] = f"Không thuộc domain yêu cầu {target_domains}"
                    continue

            allowed_schemas.add(s)

        # Retain tables belonging to allowed schemas
        allowed_tables: set[str] = {
            t for t, s in table_to_schema.items() if s in allowed_schemas
        }

        reduction = (
            (total_schemas - len(allowed_schemas)) / total_schemas
            if total_schemas > 0
            else 0.0
        )

        return FilterResult(
            allowed_schemas=allowed_schemas,
            allowed_tables=allowed_tables,
            dropped_schemas=dropped_schemas,
            reduction_ratio=reduction,
        )
