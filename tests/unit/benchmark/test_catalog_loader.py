from pathlib import Path

from t2s.benchmark.catalog_loader import load_bird_catalog_tables
from t2s.catalog import CatalogSearchDocumentBuilder


def test_bird_catalog_loader_preserves_physical_names_and_semantic_descriptions() -> None:
    catalog_tables = load_bird_catalog_tables(
        "california_schools",
        Path("data/bird_mini_dev/mini_dev_tables.json"),
    )
    satscores = next(table for table in catalog_tables if table.table_name == "satscores")
    math_score = next(column for column in satscores.columns if column.column_name == "AvgScrMath")

    assert satscores.sql_identifier == "satscores"
    assert satscores.description == "sat scores"
    assert math_score.column_name == "AvgScrMath"
    assert math_score.description == "average scores in Math"


def test_semantic_descriptions_enter_search_documents_without_changing_contracts() -> None:
    catalog_tables = load_bird_catalog_tables(
        "california_schools",
        Path("data/bird_mini_dev/mini_dev_tables.json"),
    )
    satscores = next(table for table in catalog_tables if table.table_name == "satscores")
    search_documents = CatalogSearchDocumentBuilder().build_search_documents(satscores)
    serialized_documents = " ".join(
        f"{document.title} {document.searchable_text}" for document in search_documents
    )

    assert "average scores in Math" in serialized_documents
    assert satscores.sql_identifier == "satscores"
