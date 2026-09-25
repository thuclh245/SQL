"""Table selection from a business glossary plus metadata text of the chosen variant.

The legacy selector matched question words against physical table names, which
only works when the question leaks those names.  Here a question is matched
against glossary concepts first (steward-maintained, see ``glossary.yaml``) and
then against the table/column descriptions of the metadata variant under test,
so the M0/M1/M2 ablation also measures how metadata quality affects selection.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

WORD = re.compile(r"\w+", re.UNICODE)
STOPWORDS = {
    "của",
    "các",
    "và",
    "có",
    "là",
    "cho",
    "theo",
    "trong",
    "những",
    "nào",
    "bao",
    "nhiêu",
    "mỗi",
    "từng",
    "tôi",
    "được",
    "với",
    "một",
    "không",
    "này",
    "đó",
    "the",
    "of",
    "and",
    "ngày",
    "bảng",
    "dữ",
    "liệu",
    "lưu",
    "trữ",
    "thông",
    "tin",
    "hệ",
    "thống",
    "vtnet",
}
MIN_SCORE = 0.6
RELATIVE = 0.5
MAX_TABLES = 3


def normalize(text: str) -> str:
    return unicodedata.normalize("NFC", text).lower()


def tokens(text: str) -> set[str]:
    return {w for w in WORD.findall(normalize(text)) if len(w) > 1 and w not in STOPWORDS}


@dataclass(frozen=True)
class CatalogColumn:
    name: str
    data_type: str
    description: str
    source: str


@dataclass
class CatalogTable:
    fqn: str
    duckdb_table: str
    domain: str
    description: str
    columns: dict[str, CatalogColumn] = field(default_factory=dict)


def load_catalog(path: Path) -> dict[str, CatalogTable]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, CatalogTable] = {}
    for t in raw["tables"]:
        table = CatalogTable(
            fqn=t["trino_fqn"],
            duckdb_table=t["duckdb_table"],
            domain=t.get("domain") or "",
            description=t.get("description") or "",
        )
        for c in t["columns"]:
            table.columns[c["name"].lower()] = CatalogColumn(
                name=c["name"],
                data_type=c.get("data_type") or "",
                description=c.get("description") or "",
                source=c.get("description_source") or "none",
            )
        out[table.fqn] = table
    return out


@dataclass(frozen=True)
class Glossary:
    concepts: dict[str, dict[str, Any]]
    ambiguous_terms: dict[str, dict[str, Any]]
    sensitive_terms: tuple[str, ...]
    time_expressions: dict[str, Any] = field(default_factory=dict)
    clarified_marker: str = ""

    @classmethod
    def from_file(cls, path: Path) -> Glossary:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return cls(
            concepts=dict(data.get("concepts") or {}),
            ambiguous_terms=dict(data.get("ambiguous_terms") or {}),
            sensitive_terms=tuple(data.get("sensitive_terms") or ()),
            time_expressions=dict(data.get("time_expressions") or {}),
            clarified_marker=str(data.get("clarified_marker") or ""),
        )

    def matched_concepts(self, question: str) -> dict[str, list[str]]:
        q = normalize(question)
        hits: dict[str, list[str]] = {}
        for cid, concept in self.concepts.items():
            found = [t for t in concept.get("terms", []) if _contains_term(q, t)]
            if found:
                hits[cid] = found
        return hits


def _contains_term(text: str, term: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(normalize(term))}(?!\w)", text) is not None


@dataclass(frozen=True)
class LinkResult:
    tables: list[str]
    scores: dict[str, float]
    concepts: dict[str, list[str]]
    method: str


class GlossaryLinker:
    def __init__(
        self,
        catalog: dict[str, CatalogTable],
        glossary: Glossary,
        informative_tables: set[str],
    ) -> None:
        self.catalog = catalog
        self.glossary = glossary
        # Bảng không có cột nào mang dữ liệu thật không thể trả lời câu hỏi nào.
        self.candidates = {
            fqn for fqn, t in catalog.items() if t.duckdb_table in informative_tables
        }
        self._doc_tokens = {fqn: self._table_tokens(catalog[fqn]) for fqn in self.candidates}

    @staticmethod
    def _table_tokens(table: CatalogTable) -> set[str]:
        text = " ".join(
            [table.fqn.replace(".", " ").replace("_", " "), table.description]
            + [f"{c.name.replace('_', ' ')} {c.description}" for c in table.columns.values()]
        )
        return tokens(text)

    def link(self, question: str) -> LinkResult:
        concepts = self.glossary.matched_concepts(question)
        scores: dict[str, float] = {}
        for cid in concepts:
            for fqn, weight in (self.glossary.concepts[cid].get("tables") or {}).items():
                if fqn in self.candidates:
                    scores[fqn] = scores.get(fqn, 0.0) + float(weight)
        q_tokens = tokens(question)
        for fqn, doc in self._doc_tokens.items():
            overlap = len(q_tokens & doc)
            if overlap:
                scores[fqn] = scores.get(fqn, 0.0) + min(0.5, 0.1 * overlap)
        if not scores:
            return LinkResult([], {}, concepts, "glossary")
        top = max(scores.values())
        threshold = max(MIN_SCORE, RELATIVE * top)
        ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
        chosen = [fqn for fqn, s in ranked if s >= threshold][:MAX_TABLES]
        return LinkResult(chosen, dict(ranked[:8]), concepts, "glossary")
