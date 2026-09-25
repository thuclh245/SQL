"""Keyword (BM25) and value retrieval over verified table cards.

The glossary linker is precise but only knows the concepts someone wrote down. This
module finds tables from free text the user types to describe the data they want
(the "Khác" box on the table-choice card). Every source it indexes is verified:
- table names;
- glossary labels and concept terms;
- informative column names;
- real categorical values from the profiler.

It never indexes AI-generated descriptions.

It is *not* an automatic fallback when the glossary finds nothing. On the benchmark,
questions that cannot be answered get BM25 scores (3.1–6.2) that overlap those of
answerable questions (6.7). No threshold separates the two groups, and picking a
table anyway would switch off the "no data" refusal. When evidence is that weak, the
user chooses.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field

from t2s.verified_context.linking import GlossaryLinker, fold
from t2s.verified_context.profile import DataProfiler

WORD = re.compile(r"[^\W_]+", re.UNICODE)
K1, B = 1.2, 0.75
# Giá trị ngắn hơn (vd. "1", "0") hoặc là số khớp quá nhiều câu hỏi, không mang thông tin.
MIN_VALUE_LENGTH = 3
# Chỉ tin BM25 khi điểm cao nhất đủ lớn; dưới ngưỡng coi như không tìm thấy.
MIN_BM25 = 2.0
RELATIVE_CUT = 0.5
# Giá trị thật khớp nguyên văn là bằng chứng mạnh hơn mọi điểm BM25.
VALUE_HIT_SCORE = 99.0


def _words(text: str) -> list[str]:
    return [w for w in WORD.findall(fold(text)) if len(w) > 1]


@dataclass
class BM25:
    docs: dict[str, list[str]]
    _df: Counter[str] = field(default_factory=Counter)
    _avg: float = 0.0

    def __post_init__(self) -> None:
        for words in self.docs.values():
            self._df.update(set(words))
        self._avg = sum(len(w) for w in self.docs.values()) / max(1, len(self.docs))

    def search(self, query: list[str], k: int = 5) -> list[tuple[str, float]]:
        n = len(self.docs)
        scores: dict[str, float] = {}
        for doc_id, words in self.docs.items():
            tf = Counter(words)
            score = 0.0
            for q in set(query):
                if q not in tf:
                    continue
                idf = math.log(1 + (n - self._df[q] + 0.5) / (self._df[q] + 0.5))
                norm = tf[q] * (K1 + 1) / (tf[q] + K1 * (1 - B + B * len(words) / self._avg))
                score += idf * norm
            if score > 0:
                scores[doc_id] = score
        return sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))[:k]


class TableRetriever:
    """BM25 over verified table cards plus an index of real categorical values."""

    def __init__(self, linker: GlossaryLinker, profiler: DataProfiler) -> None:
        self.linker = linker
        glossary = linker.glossary
        terms_by_table: dict[str, list[str]] = {}
        for concept in glossary.concepts.values():
            for fqn in concept.get("tables") or {}:
                terms_by_table.setdefault(fqn, []).extend(concept.get("terms") or [])
        docs: dict[str, list[str]] = {}
        self.values: dict[str, set[tuple[str, str]]] = {}
        for fqn in linker.candidates:
            table = linker.catalog[fqn]
            prof = profiler.table(table.duckdb_table)
            informative = [c for c in prof.informative_columns]
            text = " ".join(
                [
                    fqn.replace(".", " ").replace("_", " "),
                    glossary.table_labels.get(fqn, ""),
                    " ".join(terms_by_table.get(fqn, [])),
                    " ".join(c.name.replace("_", " ") for c in informative),
                ]
            )
            docs[fqn] = _words(text)
            for col in informative:
                for value in col.values or ():
                    key = fold(str(value)).strip()
                    if len(key) >= MIN_VALUE_LENGTH and not key.replace(".", "").isdigit():
                        self.values.setdefault(key, set()).add((fqn, col.name))
        self.bm25 = BM25(docs)

    def value_hits(self, question: str) -> dict[str, list[str]]:
        """Bảng có giá trị thật xuất hiện nguyên văn trong câu hỏi (vd. 'CRITICAL', 'Khu vuc 1')."""
        q = f" {' '.join(WORD.findall(fold(question)))} "
        hits: dict[str, list[str]] = {}
        for value, where in self.values.items():
            needle = f" {' '.join(WORD.findall(value))} "
            if needle.strip() and needle in q:
                for fqn, col in where:
                    hits.setdefault(fqn, []).append(f"{col}={value}")
        return hits

    def search(self, text: str, k: int = 2) -> list[tuple[str, float]]:
        """Bảng khớp một mô tả tự do; giá trị thật khớp nguyên văn được ưu tiên. Chỉ giữ
        bảng có điểm từ một nửa điểm cao nhất trở lên, để không ghim kèm bảng khớp yếu."""
        values = self.value_hits(text)
        ranked = [
            (t, s) for t, s in self.bm25.search(_words(text), k=k + len(values)) if s >= MIN_BM25
        ]
        out = [(t, VALUE_HIT_SCORE) for t in values] + [
            (t, s) for t, s in ranked if t not in values
        ]
        if not out:
            return []
        top = out[0][1]
        return [(t, s) for t, s in out if s >= RELATIVE_CUT * top][:k]
