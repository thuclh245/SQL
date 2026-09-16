from typing import Any

from t2s.catalog.catalog_models import CatalogColumn


class OpenMetadataColumnMapper:
    def map_column(
        self,
        raw_column: dict[str, Any],
        table_fqn: str,
        ordinal_position: int,
    ) -> CatalogColumn:
        column_name = str(raw_column.get("name") or raw_column.get("displayName") or "").strip()
        column_fqn = str(
            raw_column.get("fullyQualifiedName") or f"{table_fqn}.{column_name}"
        ).strip()
        constraint = str(raw_column.get("constraint") or "").strip().upper()

        raw_data_type = raw_column.get("dataType")
        raw_native_type = raw_column.get("dataTypeDisplay")

        data_type = str(raw_data_type or raw_native_type or "unknown").strip()
        native_type = str(raw_native_type).strip() if raw_native_type is not None else None

        return CatalogColumn(
            column_fqn=column_fqn,
            column_name=column_name,
            data_type=data_type,
            native_type=native_type,
            description=raw_column.get("description"),
            is_nullable=self._map_nullable(raw_column),
            is_primary_key=(constraint == "PRIMARY_KEY"),
            ordinal_position=ordinal_position,
            tags=self._extract_tag_labels(raw_column, source_name="Tag"),
            glossary_terms=self._extract_tag_labels(raw_column, source_name="Glossary"),
        )

    def _map_nullable(self, raw_column: dict[str, Any]) -> bool | None:
        if "isNullable" in raw_column and raw_column["isNullable"] is not None:
            return bool(raw_column["isNullable"])
        constraint = str(raw_column.get("constraint") or "").strip().upper()
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
