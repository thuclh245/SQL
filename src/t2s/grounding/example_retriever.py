"""Dynamic Few-Shot Example Retriever for Domain-Specific SQL In-Context Learning."""

import json
from pathlib import Path

from t2s.contracts.grounding_context import ValidatedQueryExample
from t2s.grounding.schema_retriever import tokenize_search_text


class DynamicExampleRetriever:
    """Retrieves top-k validated query examples for a database domain."""

    def __init__(self, examples_path: Path | None = None) -> None:
        self.examples_path = examples_path
        self._db_examples: dict[str, list[dict]] = {}
        if examples_path is not None:
            self._load_examples(examples_path)

    def _load_examples(self, path: Path) -> None:
        if not path.exists():
            return
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            for item in data:
                db_id = item.get("db_id")
                if db_id and "SQL" in item and "question" in item:
                    self._db_examples.setdefault(str(db_id), []).append(item)

    def retrieve_examples(
        self,
        db_id: str,
        question: str,
        k: int = 2,
        max_similarity_cutoff: float = 0.95,
    ) -> list[ValidatedQueryExample]:
        """Retrieve up to k relevant domain examples while excluding near-identical questions."""
        db_items = self._db_examples.get(db_id, [])
        if not db_items:
            return []

        q_tokens = set(tokenize_search_text(question))
        if not q_tokens:
            return []

        scored: list[tuple[float, dict]] = []
        for item in db_items:
            item_q = item.get("question", "")
            item_tokens = set(tokenize_search_text(item_q))
            if not item_tokens:
                continue

            intersection = len(q_tokens & item_tokens)
            if intersection == 0:
                continue

            union = len(q_tokens | item_tokens)
            jaccard = intersection / union if union else 0.0

            # Guard against verbatim test data leakage
            if jaccard >= max_similarity_cutoff:
                continue

            scored.append((jaccard, item))

        scored.sort(key=lambda x: x[0], reverse=True)
        top_items = scored[:k]

        return [
            ValidatedQueryExample(
                question=item["question"].strip(),
                sql=item["SQL"].strip(),
                dialect="sqlite",
            )
            for _, item in top_items
        ]
