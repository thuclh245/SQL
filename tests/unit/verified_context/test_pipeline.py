import json
from datetime import date
from pathlib import Path

import duckdb
import pytest

from t2s.verified_context.llm import Completion
from t2s.verified_context.pipeline import (
    PipelineConfig,
    VerifiedContextAssets,
    VerifiedContextPipeline,
    parse_reply,
)

TABLE = "hive__netbi__f_location_new"
FQN = "hive.netbi.f_location_new"


class ScriptedCompleter:
    def __init__(self, *replies: str) -> None:
        self.replies = list(replies)
        self.calls: list[tuple[str, str]] = []

    async def complete(self, system: str, user: str) -> Completion:
        self.calls.append((system, user))
        if not self.replies:
            raise AssertionError("LLM không được phép bị gọi thêm")
        return Completion(self.replies.pop(0), 10, 5)


@pytest.fixture
def dataset(tmp_path: Path) -> Path:
    root = tmp_path / "ds"
    (root / "generated").mkdir(parents=True)
    with duckdb.connect(str(root / "generated" / "vtnet.duckdb")) as con:
        con.execute(
            f"CREATE TABLE {TABLE} (province_code VARCHAR, province_name VARCHAR, "
            "area_code VARCHAR, dept_code VARCHAR)"
        )
        con.execute(
            f"INSERT INTO {TABLE} VALUES ('HNI','Ha Noi','AREA_1','D1'), "
            "('HNI','Ha Noi','AREA_1','D2'), ('HPG','Hai Phong','AREA_1','D1'), "
            "('DNG','Da Nang','AREA_2','D2')"
        )
    columns = [
        {"name": c, "data_type": "VARCHAR", "description": "", "description_source": "none"}
        for c in ("province_code", "province_name", "area_code", "dept_code")
    ]
    catalog = {
        "tables": [
            {"trino_fqn": FQN, "duckdb_table": TABLE, "domain": "Location", "columns": columns}
        ]
    }
    for variant in ("M0", "M1", "M2"):
        path = root / "metadata" / "variants" / variant
        path.mkdir(parents=True)
        (path / "catalog.json").write_text(json.dumps(catalog), encoding="utf-8")
    conv = root / "conventions"
    conv.mkdir()
    (conv / "glossary.yaml").write_text(
        "concepts:\n  location:\n    terms: ['tỉnh']\n"
        "    tables: {hive.netbi.f_location_new: 1.0}\n",
        encoding="utf-8",
    )
    (conv / "conventions.yaml").write_text("conventions: []\n", encoding="utf-8")
    return root


def make(
    dataset: Path, *replies: str, **cfg: object
) -> tuple[VerifiedContextPipeline, ScriptedCompleter]:
    completer = ScriptedCompleter(*replies)
    assets = VerifiedContextAssets.from_dataset(dataset)
    config = PipelineConfig(**cfg)  # type: ignore[arg-type]
    return VerifiedContextPipeline(assets, completer, config), completer


@pytest.mark.anyio
async def test_context_lists_real_values_and_grain(dataset: Path) -> None:
    pipe, llm = make(dataset, "SQL: SELECT DISTINCT province_code FROM hive.netbi.f_location_new")
    result = await pipe.run("Khu vực 1 có những tỉnh nào?", today=date(2026, 9, 24))
    system = llm.calls[0][0]
    assert "AREA_1, AREA_2" in system
    assert "province_code KHÔNG duy nhất" in system
    assert result.status == "answered"
    assert result.sql == f"SELECT DISTINCT province_code FROM {TABLE}"


@pytest.mark.anyio
async def test_empty_result_triggers_one_repair(dataset: Path) -> None:
    pipe, llm = make(
        dataset,
        f"SQL: SELECT province_code FROM {TABLE} WHERE area_code = '1'",
        f"SQL: SELECT DISTINCT province_code FROM {TABLE} WHERE area_code = 'AREA_1'",
    )
    result = await pipe.run("Khu vực 1 có những tỉnh nào?", today=date(2026, 9, 24))
    assert result.repairs == 1
    assert "Kết quả rỗng" in llm.calls[1][1]
    assert sorted(r[0] for r in result.rows) == ["HNI", "HPG"]


@pytest.mark.anyio
async def test_model_abstain_is_returned_as_declined(dataset: Path) -> None:
    pipe, _ = make(dataset, "ABSTAIN: không có dữ liệu dân số")
    result = await pipe.run("Dân số từng tỉnh?", today=date(2026, 9, 24))
    assert result.status == "abstain" and result.sql == ""


@pytest.mark.anyio
async def test_gate_declines_without_calling_the_model(dataset: Path) -> None:
    pipe, llm = make(dataset)
    result = await pipe.run("Job nào chạy chậm nhất?", today=date(2026, 9, 24))
    assert result.status == "abstain"
    assert llm.calls == []


@pytest.mark.anyio
async def test_write_statements_are_blocked_before_execution(dataset: Path) -> None:
    pipe, _ = make(dataset, f"SQL: DELETE FROM {TABLE}", verify=False)
    result = await pipe.run("Xóa các tỉnh", today=date(2026, 9, 24))
    assert result.status == "error"
    with duckdb.connect(str(dataset / "generated" / "vtnet.duckdb"), read_only=True) as con:
        assert con.execute(f"SELECT COUNT(*) FROM {TABLE}").fetchone() == (4,)


def test_parse_reply_accepts_bare_sql_and_markdown() -> None:
    assert parse_reply("```sql\nSELECT 1\n```") == ("SQL", "SELECT 1")
    assert parse_reply("CLARIFY: ý bạn là? | a | b")[0] == "CLARIFY"
    assert parse_reply("xin lỗi")[0] == "OTHER"


@pytest.mark.anyio
async def test_unresolved_convention_violation_is_not_delivered(dataset: Path) -> None:
    conv = dataset / "conventions" / "conventions.yaml"
    conv.write_text(
        "conventions:\n"
        "  - id: CONV_NO_OLD_LOCATION\n"
        "    status: accepted\n"
        "    rule: Không dùng province_name\n"
        "    applies_when: {}\n"
        "    check: {kind: forbidden_table, table: hive.netbi.f_location_new}\n",
        encoding="utf-8",
    )
    bad = f"SQL: SELECT province_code FROM {TABLE}"
    pipe, llm = make(dataset, bad, bad)
    result = await pipe.run("Có những tỉnh nào?", today=date(2026, 9, 24))
    assert result.status == "abstain"
    assert "CONV_NO_OLD_LOCATION" in result.message
    assert result.rows == [] and result.sql
    assert len(llm.calls) == 2


def test_event_tables_are_not_told_to_deduplicate(tmp_path: Path) -> None:
    from t2s.verified_context.profile import DataProfiler

    db = tmp_path / "e.duckdb"
    with duckdb.connect(str(db)) as con:
        con.execute(
            "CREATE TABLE alarms (schedule_id VARCHAR, station_code VARCHAR, date_hour VARCHAR)"
        )
        con.execute(
            "INSERT INTO alarms VALUES ('1','S1','2026-08-20-00'), ('2','S1','2026-08-20-00'), "
            "('3','S2','2026-08-20-01')"
        )
    notes = DataProfiler(db).table("alarms").grain_notes
    assert notes and "sự kiện riêng" in notes[0] and "schedule_id" in notes[0]


def _two_sources(dataset: Path) -> None:
    """Thêm bảng thứ hai và khái niệm ``choose_one`` phủ cả hai bảng."""
    with duckdb.connect(str(dataset / "generated" / "vtnet.duckdb")) as con:
        con.execute(f"CREATE TABLE hive__netbi__f_location_old AS SELECT * FROM {TABLE}")
    for variant in ("M0", "M1", "M2"):
        path = dataset / "metadata" / "variants" / variant / "catalog.json"
        catalog = json.loads(path.read_text(encoding="utf-8"))
        old = dict(catalog["tables"][0], trino_fqn="hive.netbi.f_location_old")
        old["duckdb_table"] = "hive__netbi__f_location_old"
        catalog["tables"].append(old)
        path.write_text(json.dumps(catalog), encoding="utf-8")
    (dataset / "conventions" / "glossary.yaml").write_text(
        "concepts:\n  location:\n    terms: ['tỉnh']\n"
        "    tables: {hive.netbi.f_location_new: 0.5, hive.netbi.f_location_old: 0.3}\n"
        "    choose_one: true\n"
        "table_labels:\n  hive.netbi.f_location_new: 'Danh mục tỉnh mới'\n",
        encoding="utf-8",
    )


@pytest.mark.anyio
async def test_alternative_sources_ask_the_user_before_calling_the_model(dataset: Path) -> None:
    _two_sources(dataset)
    pipe, llm = make(dataset, ask_tables=True)
    result = await pipe.run("Có những tỉnh nào?", today=date(2026, 9, 24))
    assert result.status == "clarify" and llm.calls == []
    cards = {c["fqn"]: c for c in result.table_options}
    assert set(cards) == {FQN, "hive.netbi.f_location_old"}
    assert cards[FQN]["label"] == "Danh mục tỉnh mới"
    assert "province_code" in cards[FQN]["columns"]


@pytest.mark.anyio
async def test_picked_table_is_used_and_listed_as_an_assumption(dataset: Path) -> None:
    from t2s.verified_context.pipeline import Interaction

    _two_sources(dataset)
    pipe, llm = make(dataset, f"SQL: SELECT DISTINCT province_code FROM {FQN}", ask_tables=True)
    result = await pipe.run(
        "Có những tỉnh nào?",
        today=date(2026, 9, 24),
        interaction=Interaction(tables=("netbi.f_location_new",)),
    )
    assert result.status == "answered" and result.tables == [FQN]
    assert "bạn chọn" in result.assumptions[0]
    assert "f_location_old" not in llm.calls[0][0]


@pytest.mark.anyio
async def test_mention_pins_a_table_and_unknown_mention_is_reported(dataset: Path) -> None:
    _two_sources(dataset)
    pipe, llm = make(dataset, f"SQL: SELECT DISTINCT province_code FROM {FQN}", ask_tables=True)
    result = await pipe.run("@f_location_new Có những tỉnh nào?", today=date(2026, 9, 24))
    assert result.tables == [FQN] and "@" not in llm.calls[0][1]
    missing = await pipe.run("@khong_co Có những tỉnh nào?", today=date(2026, 9, 24))
    assert missing.status == "clarify" and "@khong_co" in missing.message


@pytest.mark.anyio
async def test_free_text_clarification_skips_ambiguity_and_reaches_the_prompt(
    dataset: Path,
) -> None:
    from t2s.verified_context.pipeline import Interaction

    glossary = dataset / "conventions" / "glossary.yaml"
    glossary.write_text(
        glossary.read_text(encoding="utf-8")
        + "ambiguous_terms:\n  area:\n    pattern: 'khu vực'\n    options: ['mã', 'tên']\n",
        encoding="utf-8",
    )
    first, _ = make(dataset)
    asked = await first.run("Khu vực nào có nhiều tỉnh nhất?", today=date(2026, 9, 24))
    assert asked.status == "clarify"
    pipe, llm = make(dataset, f"SQL: SELECT area_code, COUNT(*) FROM {FQN} GROUP BY 1")
    result = await pipe.run(
        "Khu vực nào có nhiều tỉnh nhất?",
        today=date(2026, 9, 24),
        interaction=Interaction(clarification="theo area_code, đếm tỉnh không trùng"),
    )
    assert result.status == "answered"
    assert "Người dùng làm rõ: theo area_code" in llm.calls[0][1]
    assert any("area_code" in a for a in result.assumptions)


@pytest.mark.anyio
async def test_table_required_by_an_accepted_convention_is_added_to_context(
    dataset: Path,
) -> None:
    _two_sources(dataset)
    (dataset / "conventions" / "conventions.yaml").write_text(
        "conventions:\n"
        "  - id: CONV_EXCLUDE_OLD\n"
        "    status: accepted\n"
        "    rule: Loại tỉnh đã có trong bảng cũ\n"
        "    applies_when: {question_terms: ['tỉnh mới']}\n"
        "    check: {kind: requires_anti_join, table: hive.netbi.f_location_old, "
        "key: province_code}\n",
        encoding="utf-8",
    )
    pipe, llm = make(dataset, "ABSTAIN: không cần")
    result = await pipe.run("@f_location_new Liệt kê tỉnh mới", today=date(2026, 9, 24))
    assert "hive.netbi.f_location_old" in result.tables
    assert "f_location_old" in llm.calls[0][0]


@pytest.mark.anyio
async def test_follow_up_keeps_previous_tables_and_sql(dataset: Path) -> None:
    from t2s.verified_context.pipeline import Interaction

    _two_sources(dataset)
    pipe, llm = make(
        dataset, f"SQL: SELECT province_code FROM {FQN} WHERE area_code = 'AREA_1'", ask_tables=True
    )
    previous = f"SELECT DISTINCT province_code FROM {FQN}"
    result = await pipe.run(
        "Chỉ lấy khu vực 1",
        today=date(2026, 9, 24),
        interaction=Interaction(
            previous_question="Có những tỉnh nào?",
            previous_sql=previous,
            previous_tables=(FQN,),
        ),
    )
    assert result.status == "answered" and result.tables[0] == FQN
    assert previous in llm.calls[0][1] and "Ngữ cảnh lượt trước" in llm.calls[0][1]
    assert result.assumptions[0].startswith("Tiếp nối câu hỏi")


@pytest.mark.anyio
async def test_unaccented_question_links_like_the_accented_one(dataset: Path) -> None:
    pipe, llm = make(dataset, f"SQL: SELECT DISTINCT province_code FROM {FQN}")
    result = await pipe.run("Co nhung tinh nao?", today=date(2026, 9, 24))
    assert result.tables == [FQN] and llm.calls


@pytest.mark.anyio
async def test_free_text_table_hint_finds_tables_by_label_and_values(dataset: Path) -> None:
    from t2s.verified_context.pipeline import Interaction

    _two_sources(dataset)
    pipe, _ = make(dataset, f"SQL: SELECT DISTINCT province_code FROM {FQN}", ask_tables=True)
    by_label = await pipe.run(
        "Có những tỉnh nào?",
        today=date(2026, 9, 24),
        interaction=Interaction(table_hint="danh mục tỉnh mới"),
    )
    assert by_label.tables[0] == FQN
    hits = pipe.retriever.value_hits("các tỉnh thuộc AREA_2")
    assert FQN in hits and any("area_code=area_2" in h for h in hits[FQN])
