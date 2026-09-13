from typing import Any

from t2s.catalog.catalog_models import CatalogColumn


class OpenMetadataColumnMapper:
    def map_column(
        self,
        raw_column: dict[str, Any],
        table_fqn: str,
        ordinal_position: int,
    ) -> CatalogColumn:
        column_name = str(raw_column.get("name") or raw_column.get("displayName") or "")
        column_fqn = str(raw_column.get("fullyQualifiedName") or f"{table_fqn}.{column_name}")
        constraint = str(raw_column.get("constraint") or "").upper()
        return CatalogColumn(
            column_fqn=column_fqn,
            column_name=column_name,
            data_type=str(
                raw_column.get("dataTypeDisplay") or raw_column.get("dataType") or "unknown"
            ),
            description=raw_column.get("description"),
            is_nullable=self._map_nullable(raw_column),
            is_primary_key=constraint == "PRIMARY_KEY",
            ordinal_position=ordinal_position,
            tags=self._extract_tag_labels(raw_column, source_name="Tag"),
            glossary_terms=self._extract_tag_labels(raw_column, source_name="Glossary"),
        )

    def _map_nullable(self, raw_column: dict[str, Any]) -> bool | None:
        if "isNullable" in raw_column:
            return bool(raw_column["isNullable"])
        constraint = str(raw_column.get("constraint") or "").upper()
        if constraint in {"NOT_NULL", "PRIMARY_KEY"}:
            return False
        return None

    def _extract_tag_labels(self, raw_entity: dict[str, Any], source_name: str) -> list[str]:
        tag_labels: list[str] = []
        for raw_tag in raw_entity.get("tags") or []:
            if not isinstance(raw_tag, dict):
                continue
            if raw_tag.get("source") != source_name:
                continue
            tag_label = raw_tag.get("tagFQN") or raw_tag.get("label") or raw_tag.get("name")
            if tag_label:
                tag_labels.append(str(tag_label))
        return tag_labels
