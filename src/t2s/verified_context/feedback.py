"""Interaction log, user feedback and the review queue that turns answers into examples.

Every answered or declined turn is recorded. A user marks a turn "Đúng" or "Báo sai";
both land in the review queue. Only a reviewer (DE) can approve a turn into an
example, optionally correcting its SQL first. Approved examples are the only ones a
later retrieval step may put into a prompt.

Questions that belong to an evaluation set (benchmark, held-out) are blocked from
becoming examples: an example leaking into the prompt would make the evaluation
measure recall of the answer instead of the system.

The local implementation stores everything in one SQLite file; ``InteractionStore``
is the seam for a production store.
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
import unicodedata
import uuid
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

VERDICTS = ("correct", "wrong")
# Trạng thái của một lượt trong hàng chờ duyệt.
PENDING, APPROVED, REJECTED, BLOCKED = "pending", "approved", "rejected", "blocked_eval_set"

SCHEMA = """
CREATE TABLE IF NOT EXISTS turns (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    db_id TEXT NOT NULL,
    model TEXT NOT NULL,
    question TEXT NOT NULL,
    interaction TEXT NOT NULL,
    status TEXT NOT NULL,
    sql TEXT NOT NULL,
    tables TEXT NOT NULL,
    assumptions TEXT NOT NULL,
    message TEXT NOT NULL,
    row_count INTEGER NOT NULL,
    latency_ms INTEGER NOT NULL,
    tokens INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS feedback (
    turn_id TEXT PRIMARY KEY REFERENCES turns(id),
    verdict TEXT NOT NULL,
    note TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reviews (
    turn_id TEXT PRIMARY KEY REFERENCES turns(id),
    status TEXT NOT NULL,
    sql TEXT NOT NULL,
    note TEXT NOT NULL,
    reviewer TEXT NOT NULL,
    reviewed_at TEXT NOT NULL
);
"""


class ReviewError(ValueError):
    """A review action that the rules do not allow (unknown turn, evaluation question)."""


def question_key(text: str) -> str:
    """Normalised question used to recognise evaluation-set questions."""
    text = unicodedata.normalize("NFC", text).lower()
    return re.sub(r"[\W_]+", " ", text).strip()


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class InteractionStore(Protocol):
    def record_turn(self, **turn: Any) -> str: ...

    def add_feedback(self, turn_id: str, verdict: str, note: str = "") -> dict[str, Any]: ...

    def review_items(self, status: str = PENDING) -> list[dict[str, Any]]: ...

    def approve(
        self, turn_id: str, *, sql: str | None = None, note: str = "", reviewer: str = "DE"
    ) -> dict[str, Any]: ...

    def reject(self, turn_id: str, *, note: str = "", reviewer: str = "DE") -> dict[str, Any]: ...

    def approved_examples(self) -> list[dict[str, Any]]: ...


class SQLiteInteractionStore:
    def __init__(self, path: Path, blocked_questions: Iterable[str] = ()) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.blocked = {question_key(q) for q in blocked_questions if q}
        self._lock = threading.Lock()
        with self._connect() as con:
            con.executescript(SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """Một kết nối cho mỗi thao tác: commit khi xong, rollback khi lỗi, luôn đóng."""
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        try:
            with con:
                yield con
        finally:
            con.close()

    def is_blocked(self, question: str) -> bool:
        return question_key(question) in self.blocked

    # ------------------------------------------------------------ writes

    def record_turn(
        self,
        *,
        db_id: str,
        model: str,
        question: str,
        interaction: dict[str, Any] | None,
        status: str,
        sql: str,
        tables: list[str],
        assumptions: list[str],
        message: str,
        row_count: int,
        latency_ms: int,
        tokens: int,
    ) -> str:
        turn_id = uuid.uuid4().hex[:12]
        with self._lock, self._connect() as con:
            con.execute(
                "INSERT INTO turns VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    turn_id,
                    _now(),
                    db_id,
                    model,
                    question,
                    json.dumps(interaction or {}, ensure_ascii=False),
                    status,
                    sql,
                    json.dumps(tables, ensure_ascii=False),
                    json.dumps(assumptions, ensure_ascii=False),
                    message,
                    row_count,
                    latency_ms,
                    tokens,
                ),
            )
        return turn_id

    def add_feedback(self, turn_id: str, verdict: str, note: str = "") -> dict[str, Any]:
        if verdict not in VERDICTS:
            raise ReviewError(f"verdict phải là một trong {VERDICTS}")
        with self._lock, self._connect() as con:
            self._turn(con, turn_id)
            con.execute(
                "INSERT INTO feedback VALUES (?,?,?,?) ON CONFLICT(turn_id) DO UPDATE SET "
                "verdict=excluded.verdict, note=excluded.note, created_at=excluded.created_at",
                (turn_id, verdict, note.strip(), _now()),
            )
        return self.item(turn_id)

    def approve(
        self, turn_id: str, *, sql: str | None = None, note: str = "", reviewer: str = "DE"
    ) -> dict[str, Any]:
        with self._lock, self._connect() as con:
            turn = self._turn(con, turn_id)
            if self.is_blocked(turn["question"]):
                raise ReviewError(
                    "Câu hỏi trùng với bộ đánh giá (benchmark/held-out); không được dùng làm "
                    "câu mẫu vì sẽ làm sai lệch kết quả đo."
                )
            final_sql = (sql if sql is not None else turn["sql"]).strip()
            if not final_sql:
                raise ReviewError("Lượt này chưa có SQL; nhập SQL đúng trước khi duyệt.")
            self._set_review(con, turn_id, APPROVED, final_sql, note, reviewer)
        return self.item(turn_id)

    def reject(self, turn_id: str, *, note: str = "", reviewer: str = "DE") -> dict[str, Any]:
        with self._lock, self._connect() as con:
            turn = self._turn(con, turn_id)
            self._set_review(con, turn_id, REJECTED, turn["sql"], note, reviewer)
        return self.item(turn_id)

    @staticmethod
    def _set_review(
        con: sqlite3.Connection, turn_id: str, status: str, sql: str, note: str, reviewer: str
    ) -> None:
        con.execute(
            "INSERT INTO reviews VALUES (?,?,?,?,?,?) ON CONFLICT(turn_id) DO UPDATE SET "
            "status=excluded.status, sql=excluded.sql, note=excluded.note, "
            "reviewer=excluded.reviewer, reviewed_at=excluded.reviewed_at",
            (turn_id, status, sql, note.strip(), reviewer, _now()),
        )

    # ------------------------------------------------------------ reads

    @staticmethod
    def _turn(con: sqlite3.Connection, turn_id: str) -> sqlite3.Row:
        row = con.execute("SELECT * FROM turns WHERE id = ?", (turn_id,)).fetchone()
        if row is None:
            raise ReviewError(f"Không có lượt hỏi {turn_id}")
        return row

    _SELECT = (
        "SELECT t.*, f.verdict, f.note AS feedback_note, f.created_at AS feedback_at, "
        "r.status AS review_status, r.sql AS reviewed_sql, r.note AS review_note, "
        "r.reviewer, r.reviewed_at FROM turns t JOIN feedback f ON f.turn_id = t.id "
        "LEFT JOIN reviews r ON r.turn_id = t.id"
    )

    def _row(self, row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        for key in ("interaction", "tables", "assumptions"):
            item[key] = json.loads(item[key])
        blocked = self.is_blocked(item["question"])
        item["status_in_queue"] = item["review_status"] or (BLOCKED if blocked else PENDING)
        item["blocked_eval_set"] = blocked
        return item

    def item(self, turn_id: str) -> dict[str, Any]:
        with self._connect() as con:
            row = con.execute(self._SELECT + " WHERE t.id = ?", (turn_id,)).fetchone()
            if row is None:
                turn = self._turn(con, turn_id)
                return {"id": turn["id"], "verdict": None, "status_in_queue": None}
        return self._row(row)

    def review_items(self, status: str = PENDING) -> list[dict[str, Any]]:
        """Turns with user feedback, newest first. ``status``: pending | approved |
        rejected | blocked_eval_set | all."""
        with self._connect() as con:
            rows = con.execute(self._SELECT + " ORDER BY f.created_at DESC").fetchall()
        items = [self._row(r) for r in rows]
        return items if status == "all" else [i for i in items if i["status_in_queue"] == status]

    def approved_examples(self) -> list[dict[str, Any]]:
        return [
            {
                "turn_id": i["id"],
                "question": i["question"],
                "sql": i["reviewed_sql"],
                "tables": i["tables"],
                "interaction": i["interaction"],
                "reviewer": i["reviewer"],
                "reviewed_at": i["reviewed_at"],
            }
            for i in self.review_items(APPROVED)
        ]

    def stats(self) -> dict[str, int]:
        with self._connect() as con:
            turns = con.execute("SELECT COUNT(*) FROM turns").fetchone()[0]
        items = self.review_items("all")
        out = {"turns": turns, "feedback": len(items)}
        for key in (PENDING, APPROVED, REJECTED, BLOCKED):
            out[key] = sum(i["status_in_queue"] == key for i in items)
        return out
