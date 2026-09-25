from t2s.verified_context.linking import fold, has_diacritics
from t2s.verified_context.retrieval import BM25


def test_fold_removes_vietnamese_diacritics_only_when_asked() -> None:
    assert fold("Tỉnh Đà Nẵng") == "tinh da nang"
    assert has_diacritics("tỉnh") and not has_diacritics("tinh nao")


def test_bm25_ranks_the_document_with_the_rarer_matching_word_first() -> None:
    index = BM25({"kpi": ["kpi", "cell", "throughput"], "alarm": ["canh", "bao", "cell"]})
    assert index.search(["throughput", "cell"])[0][0] == "kpi"
    assert index.search(["khong", "co"]) == []
