from typing import Any


def build_sql_candidate_json_schema() -> dict[str, Any]:
    dialect_enum = ["postgres", "clickhouse", "starrocks", "sqlite"]
    return {
        "name": "sql_candidate",
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "sql",
                "dialect",
                "referenced_tables",
                "referenced_columns",
                "expected_columns",
                "assumptions",
                "unresolved",
            ],
            "properties": {
                "sql": {"type": "string", "minLength": 1},
                "dialect": {"type": "string", "enum": dialect_enum},
                "referenced_tables": {"type": "array", "items": {"type": "string"}},
                "referenced_columns": {"type": "array", "items": {"type": "string"}},
                "expected_columns": {"type": "array", "items": {"type": "string"}},
                "assumptions": {"type": "array", "items": {"type": "string"}},
                "unresolved": {"type": "array", "items": {"type": "string"}},
            },
        },
        "strict": True,
    }
