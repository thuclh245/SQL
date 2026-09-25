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


def fold(text: str) -> str:
    """Bỏ dấu tiếng Việt (vd. để so câu hỏi gõ không dấu với glossary)."""
    text = unicodedata.normalize("NFD", text.lower()).replace("đ", "d")
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def has_diacritics(text: str) -> bool:
    return fold(text) != unicodedata.normalize("NFD", text.lower())


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
    # Nhãn ngắn, đã được người duyệt, hiển thị trên thẻ chọn bảng (không dùng mô tả AI).
    table_labels: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_file(cls, path: Path) -> Glossary:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return cls(
            concepts=dict(data.get("concepts") or {}),
            ambiguous_terms=dict(data.get("ambiguous_terms") or {}),
            sensitive_terms=tuple(data.get("sensitive_terms") or ()),
            time_expressions=dict(data.get("time_expressions") or {}),
            clarified_marker=str(data.get("clarified_marker") or ""),
            table_labels={str(k): str(v) for k, v in (data.get("table_labels") or {}).items()},
        )

    def matched_concepts(self, question: str, *, folded: bool = False) -> dict[str, list[str]]:
        """``folded``: so khớp sau khi bỏ dấu cả hai phía; chỉ dùng cho câu hỏi gõ không dấu,
        vì bỏ dấu câu có dấu sẽ gộp các từ khác nghĩa ("tỉnh"/"tính")."""
        q = fold(question) if folded else normalize(question)
        hits: dict[str, list[str]] = {}
        for cid, concept in self.concepts.items():
            found = [
                t for t in concept.get("terms", []) if _contains_term(q, fold(t) if folded else t)
            ]
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
        self._doc_tokens_folded = {
            fqn: {fold(t) for t in doc} for fqn, doc in self._doc_tokens.items()
        }

    @staticmethod
    def _table_tokens(table: CatalogTable) -> set[str]:
        text = " ".join(
            [table.fqn.replace(".", " ").replace("_", " "), table.description]
            + [f"{c.name.replace('_', ' ')} {c.description}" for c in table.columns.values()]
        )
        return tokens(text)

    def link_folded(self, question: str) -> LinkResult:
        """Như ``link`` cho câu hỏi không dấu: glossary và mô tả được so sau khi bỏ dấu."""
        return self.link(question, folded=True)

    def link(self, question: str, *, folded: bool = False) -> LinkResult:
        concepts = self.glossary.matched_concepts(question, folded=folded)
        scores: dict[str, float] = {}
        for cid in concepts:
            for fqn, weight in (self.glossary.concepts[cid].get("tables") or {}).items():
                if fqn in self.candidates:
                    scores[fqn] = scores.get(fqn, 0.0) + float(weight)
        q_tokens = {fold(t) for t in tokens(question)} if folded else tokens(question)
        docs = self._doc_tokens_folded if folded else self._doc_tokens
        for fqn, doc in docs.items():
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


def alternatives(linker: GlossaryLinker, link: LinkResult) -> list[str]:
    """Bảng mà người dùng nên chọn giữa, khi hệ thống không có căn cứ để tự chọn.

    Chỉ hỏi khi một khái niệm ``choose_one`` trong glossary (vd. "lưu lượng" có ở cả
    KPI 5G và 4G) là nguồn dữ liệu duy nhất của câu hỏi: không khái niệm nào khác ủng hộ
    một bảng trong nhóm, và mọi bảng đã chọn đều thuộc nhóm đó. Khi câu hỏi còn nhắc tới
    bảng khác, khái niệm này chỉ là thuộc tính để JOIN, không phải lựa chọn nguồn.

    Không đưa ra ứng viên yếu (chỉ khớp mô tả): trên benchmark, trường hợp đó chỉ gặp ở
    câu không trả lời được, nơi từ chối mới là đúng.
    """
    concepts = linker.glossary.concepts
    for cid in link.concepts:
        concept = concepts[cid]
        if not concept.get("choose_one"):
            continue
        group = [t for t in concept.get("tables") or {} if t in linker.candidates]
        if len(group) < 2 or not set(link.tables) <= set(group):
            continue
        support = {
            t: sum(
                float((concepts[o].get("tables") or {}).get(t, 0))
                for o in link.concepts
                if o != cid
            )
            for t in group
        }
        if max(support.values()) == 0:
            return group
    return []
