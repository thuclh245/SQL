"""Read the OpenMetadata-style Markdown supplied with the sample data."""
from pathlib import Path

SOURCE_NOTE = Path(__file__).resolve().parent.parent / "Ghi chú mới.md"
PREFIX = "VTNet Datalake Presto.hive."

def read_source_catalog():
    tables = {}
    schemas = {}
    for line in SOURCE_NOTE.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| ") or line.startswith("| ---"):
            continue
        values = [part.strip() for part in line.strip().split("|")[1:-1]]
        if len(values) < 16:
            continue
        kind = values[12]
        fqname = values[13]
        if kind == "databaseSchema":
            schemas[values[0]] = {"schema": values[0], "description": values[2], "source_fqn": fqname}
        elif kind == "table":
            short = fqname.removeprefix(PREFIX)
            tables[short] = {"table": short, "source_fqn": fqname, "description": values[2], "tags": values[4], "columns": []}
        elif kind == "column":
            short = ".".join(fqname.removeprefix(PREFIX).split(".")[:-1])
            if short in tables:
                tables[short]["columns"].append({"name": values[0], "description": values[2], "data_type_display": values[14], "data_type": values[15], "tags": values[4]})
    if len(schemas) != 3 or len(tables) != 8 or sum(len(t["columns"]) for t in tables.values()) != 179:
        raise ValueError("Source metadata inventory changed; review parsing before generating")
    return {"source_file": str(SOURCE_NOTE.relative_to(SOURCE_NOTE.parent.parent)), "schemas": list(schemas.values()), "tables": list(tables.values())}
