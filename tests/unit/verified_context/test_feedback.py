from pathlib import Path

import pytest

from t2s.verified_context.feedback import ReviewError, SQLiteInteractionStore

TURN = {
    "db_id": "vtnet_mini",
    "model": "m",
    "interaction": {"clarification": "region"},
    "status": "answered",
    "sql": "SELECT 1",
    "tables": ["hive.gnoc.gnoc"],
    "assumptions": ["Bảng dữ liệu: gnoc.gnoc"],
    "message": "",
    "row_count": 1,
    "latency_ms": 10,
    "tokens": 5,
}


def store(tmp_path: Path) -> SQLiteInteractionStore:
    return SQLiteInteractionStore(tmp_path / "log.sqlite", ["Khu vực nào có nhiều cảnh báo nhất?"])


def test_only_turns_with_feedback_enter_the_review_queue(tmp_path: Path) -> None:
    s = store(tmp_path)
    quiet = s.record_turn(question="Có bao nhiêu trạm?", **TURN)
    judged = s.record_turn(question="Có bao nhiêu cảnh báo?", **TURN)
    s.add_feedback(judged, "wrong", "thiếu điều kiện còn mở")
    items = s.review_items()
    assert [i["id"] for i in items] == [judged]
    assert items[0]["feedback_note"] == "thiếu điều kiện còn mở"
    assert s.stats()["turns"] == 2 and quiet


def test_approval_can_correct_sql_and_becomes_an_example(tmp_path: Path) -> None:
    s = store(tmp_path)
    tid = s.record_turn(question="Có bao nhiêu cảnh báo còn mở?", **TURN)
    s.add_feedback(tid, "wrong")
    s.approve(tid, sql="SELECT COUNT(*) FROM gnoc WHERE uptime_date IS NULL", note="sửa")
    assert s.review_items() == []
    [example] = s.approved_examples()
    assert example["sql"].endswith("IS NULL") and example["tables"] == ["hive.gnoc.gnoc"]


def test_evaluation_questions_cannot_become_examples(tmp_path: Path) -> None:
    s = store(tmp_path)
    tid = s.record_turn(question="khu vực nào có nhiều cảnh báo nhất", **TURN)
    item = s.add_feedback(tid, "correct")
    assert item["status_in_queue"] == "blocked_eval_set"
    with pytest.raises(ReviewError):
        s.approve(tid)
    assert s.approved_examples() == []


def test_unknown_turn_and_bad_verdict_are_rejected(tmp_path: Path) -> None:
    s = store(tmp_path)
    with pytest.raises(ReviewError):
        s.add_feedback("nope", "correct")
    tid = s.record_turn(question="q", **TURN)
    with pytest.raises(ReviewError):
        s.add_feedback(tid, "maybe")
