"""Verified-context Text-to-SQL pipeline.

    linking → gates → context → LLM → normalise → guard → execute → verify/repair

Every stage records a :class:`BlockTrace`, and every contribution can be turned
off through :class:`PipelineConfig` for ablation.  SQL produced by the model is
never rewritten semantically: the only deterministic rewrite maps table names to
their physical DuckDB names.  Anything else wrong is reported back to the model
by the verifier, so the final SQL is always SQL the model stands behind.
"""

from __future__ import annotations

import re
import time
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import duckdb
import sqlglot
from sqlglot import exp

from t2s.verified_context.conventions import Convention, ConventionRegistry
from t2s.verified_context.gates import (
    GateDecision,
    ambiguity_gate,
    coverage_gate,
    sensitive_gate,
)
from t2s.verified_context.linking import CatalogTable, Glossary, GlossaryLinker, load_catalog
from t2s.verified_context.llm import TextCompleter
from t2s.verified_context.profile import DataProfiler
from t2s.verified_context.prompt import (
    TableContext,
    build_system_prompt,
    repair_message,
    table_context,
)

METADATA_VARIANTS = ("M0", "M1", "M2")
FALLBACK_TABLES = ["hive.npms.kpi_access5g_5g_cell_peak_view"]
UI_ROW_LIMIT = 100


@dataclass(frozen=True)
class PipelineConfig:
    name: str = "full"
    linker: str = "glossary"  # glossary | oracle
    metadata: str = "M2"  # M0 | M1 | M2
    profile: bool = True  # cột có dữ liệu, giá trị, phạm vi, grain
    conventions: bool = True  # quy ước nghiệp vụ trong prompt
    definitions: bool = True  # định nghĩa thuật ngữ từ glossary (note của khái niệm)
    verify: bool = True  # checker quy ước + lỗi thực thi + kết quả rỗng → vòng sửa
    gates: bool = True  # policy / mơ hồ / phạm vi thời gian + hợp đồng ABSTAIN/CLARIFY
    max_repairs: int = 1

    def __post_init__(self) -> None:
        if self.metadata not in METADATA_VARIANTS:
            raise ValueError(f"metadata phải thuộc {METADATA_VARIANTS}")
        if self.linker not in ("glossary", "oracle"):
            raise ValueError("linker phải là 'glossary' hoặc 'oracle'")


@dataclass
class BlockTrace:
    name: str
    status: str  # done | skipped | warning | failed | declined
    detail: str
    data: dict[str, Any] = field(default_factory=dict)
    elapsed_ms: int = 0


@dataclass
class Attempt:
    sql: str
    error: str | None
    row_count: int
    violations: list[dict[str, Any]]

    @property
    def problems(self) -> list[str]:
        out = [f"Lỗi thực thi: {self.error.splitlines()[0]}"] if self.error else []
        for v in self.violations:
            out.append(
                f"Vi phạm quy ước {v['convention_id']} ({v['rule']}): {'; '.join(v['messages'])}"
            )
        if not self.error and self.row_count == 0:
            out.append(
                "Kết quả rỗng: kiểm tra lại giá trị literal (dùng đúng giá trị thật đã liệt kê), "
                "định dạng thời gian và điều kiện lọc."
            )
        return out

    def rank(self) -> tuple[int, int, int]:
        return (self.error is not None, len(self.violations), self.row_count == 0)


@dataclass
class PipelineResult:
    status: str  # answered | abstain | clarify | error
    question: str
    config: str
    sql: str = ""
    columns: list[str] = field(default_factory=list)
    rows: list[list[Any]] = field(default_factory=list)
    row_count: int = 0
    message: str = ""
    options: list[str] = field(default_factory=list)
    tables: list[str] = field(default_factory=list)
    conventions: list[str] = field(default_factory=list)
    violations: list[dict[str, Any]] = field(default_factory=list)
    repairs: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0
    trace: list[BlockTrace] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class VerifiedContextAssets:
    db_path: Path
    profiler: DataProfiler
    catalogs: dict[str, dict[str, CatalogTable]]
    glossary: Glossary
    registry: ConventionRegistry
    table_map: dict[str, str]

    @classmethod
    def from_dataset(cls, root: Path) -> VerifiedContextAssets:
        """``root`` là thư mục dataset (vd. sample data/synthetic/vtnet-mini)."""
        db_path = root / "generated" / "vtnet.duckdb"
        profiler = DataProfiler(db_path)
        catalogs = {
            v: load_catalog(root / "metadata" / "variants" / v / "catalog.json")
            for v in METADATA_VARIANTS
        }
        table_map: dict[str, str] = {}
        for t in catalogs["M1"].values():
            duck = t.duckdb_table
            for alias in (t.fqn, t.fqn.split(".", 1)[1], t.fqn.rsplit(".", 1)[1], duck):
                table_map.setdefault(alias.lower(), duck)
        return cls(
            db_path=db_path,
            profiler=profiler,
            catalogs=catalogs,
            glossary=Glossary.from_file(root / "conventions" / "glossary.yaml"),
            registry=ConventionRegistry.from_file(root / "conventions" / "conventions.yaml"),
            table_map=table_map,
        )


def parse_reply(text: str) -> tuple[str, str]:
    body = re.sub(r"```(?:sql)?", "", text).strip()
    m = re.match(r"^(SQL|CLARIFY|ABSTAIN)\s*:\s*(.*)$", body, re.S | re.I)
    if m:
        return m.group(1).upper(), m.group(2).strip()
    if re.match(r"(?is)^\s*(with|select)\b", body):
        return "SQL", body
    return "OTHER", body


class VerifiedContextPipeline:
    def __init__(
        self,
        assets: VerifiedContextAssets,
        completer: TextCompleter,
        config: PipelineConfig | None = None,
    ) -> None:
        self.assets = assets
        self.completer = completer
        self.config = config or PipelineConfig()
        informative = {
            t for t in assets.profiler.tables if assets.profiler.table(t).informative_columns
        }
        self.linker = GlossaryLinker(
            assets.catalogs[self.config.metadata], assets.glossary, informative
        )

    # ------------------------------------------------------------ stages

    def _link(
        self, question: str, oracle_tables: list[str] | None
    ) -> tuple[list[str], set[str], BlockTrace]:
        t0 = time.perf_counter()
        link = self.linker.link(question)
        if self.config.linker == "oracle" and oracle_tables:
            tables, method = list(oracle_tables), "oracle"
        else:
            tables, method = link.tables, "glossary"
        trace = BlockTrace(
            "linking",
            "done" if tables else "warning",
            f"{method}: {', '.join(tables) or 'không tìm thấy bảng có dữ liệu liên quan'}",
            {"tables": tables, "scores": link.scores, "concepts": link.concepts, "method": method},
            _ms(t0),
        )
        return tables, set(link.concepts), trace

    def _gate(
        self, question: str, tables: list[str], concepts: set[str], today: date
    ) -> tuple[GateDecision | None, BlockTrace]:
        t0 = time.perf_counter()
        checks: list[dict[str, str]] = []
        decision = sensitive_gate(question, self.assets.glossary)
        checks.append(
            {"rule": "Dữ liệu định danh cá nhân", "status": "failed" if decision else "passed"}
        )
        if decision is None:
            decision = ambiguity_gate(question, self.assets.glossary, concepts)
            checks.append(
                {"rule": "Thuật ngữ nhiều nghĩa", "status": "failed" if decision else "passed"}
            )
        if decision is None and not tables:
            decision = GateDecision(
                "abstain",
                "no_data",
                "Không có bảng nào chứa dữ liệu thật cho khái niệm được hỏi.",
            )
            checks.append({"rule": "Có bảng dữ liệu liên quan", "status": "failed"})
        ranges: dict[str, tuple[str, str]] = {}
        if decision is None:
            ranges = self.assets.profiler.data_range([self._duck(t) for t in tables])
            decision, periods = coverage_gate(question, ranges, today, self.assets.glossary)
            checks.append(
                {
                    "rule": "Thời gian nằm trong phạm vi dữ liệu",
                    "status": "failed" if decision else "passed",
                    "detail": ", ".join(f"{p.start}→{p.end}" for p in periods)
                    or "không nêu thời gian",
                }
            )
        status = "declined" if decision else "done"
        detail = decision.message if decision else "Không có lý do để từ chối hoặc hỏi lại"
        return decision, BlockTrace(
            "gates", status, detail, {"checks": checks, "data_range": ranges}, _ms(t0)
        )

    def _context(
        self, question: str, tables: list[str], concepts: set[str]
    ) -> tuple[str, list[TableContext], list[Convention], BlockTrace]:
        t0 = time.perf_counter()
        cfg = self.config
        catalog = self.assets.catalogs[cfg.metadata]
        contexts = [
            table_context(
                catalog[t],
                self.assets.profiler.table(catalog[t].duckdb_table),
                question=question,
                use_profile=cfg.profile,
                with_descriptions=cfg.metadata != "M0",
            )
            for t in tables
            if t in catalog
        ]
        shown = {c for ctx in contexts for c in ctx.shown_columns}
        conventions = (
            self.assets.registry.select(question=question, tables=tables, columns=shown)
            if cfg.conventions
            else []
        )
        definitions = self._definitions(concepts, tables) if cfg.definitions else []
        system = build_system_prompt(
            contexts, conventions, contract=cfg.gates, definitions=definitions
        )
        trace = BlockTrace(
            "context",
            "done",
            f"{len(contexts)} bảng, {len(shown)} cột, {len(conventions)} quy ước, "
            f"metadata {cfg.metadata}{', có profiler' if cfg.profile else ''}",
            {
                "tables": {ctx.duckdb_table: ctx.lines[1:] for ctx in contexts},
                "grain": {ctx.duckdb_table: ctx.grain_notes for ctx in contexts if ctx.grain_notes},
                "conventions": [c["rule"] for c in conventions],
                "definitions": definitions,
                "values": self._value_dictionary(contexts) if cfg.profile else {},
                "system_prompt": system,
            },
            _ms(t0),
        )
        return system, contexts, conventions, trace

    def _definitions(self, concepts: set[str], tables: list[str]) -> list[str]:
        """Glossary notes of the concepts the question mentions, for tables in scope."""
        scope = {t.lower() for t in tables}
        out = []
        for cid in sorted(concepts):
            concept = self.assets.glossary.concepts.get(cid) or {}
            note = concept.get("note")
            if note and {t.lower() for t in concept.get("tables") or {}} & scope:
                out.append(str(note))
        return out

    def _value_dictionary(self, contexts: list[TableContext]) -> dict[str, list[str]]:
        out = {}
        for ctx in contexts:
            prof = self.assets.profiler.table(ctx.duckdb_table)
            for name in sorted(ctx.shown_columns):
                col = prof.columns[name]
                if col.values:
                    out[f"{ctx.duckdb_table.rsplit('__', 1)[-1]}.{col.name}"] = list(col.values)
        return out

    def _duck(self, fqn: str) -> str:
        return self.assets.table_map.get(fqn.lower(), fqn)

    def normalise(self, sql: str) -> str:
        """Map trino/short table names to DuckDB physical names; nothing else is touched."""
        try:
            tree = sqlglot.parse_one(sql, dialect="duckdb")
        except sqlglot.errors.ParseError:
            return sql
        ctes = {c.alias_or_name.lower() for c in tree.find_all(exp.CTE)}
        for tbl in tree.find_all(exp.Table):
            ref = ".".join(p for p in (tbl.catalog, tbl.db, tbl.name) if p).lower()
            if tbl.name.lower() in ctes:
                continue
            target = self.assets.table_map.get(ref) or self.assets.table_map.get(tbl.name.lower())
            if target:
                tbl.set("this", exp.to_identifier(target))
                tbl.set("db", None)
                tbl.set("catalog", None)
        return tree.sql(dialect="duckdb")

    @staticmethod
    def guard(sql: str) -> str | None:
        try:
            statements = [s for s in sqlglot.parse(sql, dialect="duckdb") if s is not None]
        except sqlglot.errors.ParseError as exc:
            return f"Không phân tích được SQL: {str(exc).splitlines()[0]}"
        if len(statements) != 1:
            return "Chỉ chấp nhận đúng một câu lệnh"
        tree = statements[0]
        forbidden = (
            exp.Insert,
            exp.Update,
            exp.Delete,
            exp.Drop,
            exp.Create,
            exp.Alter,
            exp.Command,
        )
        if isinstance(tree, forbidden) or any(tree.find(f) for f in forbidden):
            return "Chỉ cho phép câu lệnh đọc (SELECT)"
        if not isinstance(tree, (exp.Select, exp.Union, exp.Intersect, exp.Except)):
            return "Chỉ cho phép câu lệnh SELECT"
        return None

    def execute(self, sql: str) -> tuple[list[str], list[list[Any]], str | None]:
        try:
            with duckdb.connect(str(self.assets.db_path), read_only=True) as con:
                cur = con.execute(sql)
                columns = [d[0] for d in cur.description] if cur.description else []
                return columns, [list(r) for r in cur.fetchall()], None
        except duckdb.Error as exc:
            return [], [], str(exc)

    # ------------------------------------------------------------ run

    async def run(
        self,
        question: str,
        *,
        oracle_tables: list[str] | None = None,
        today: date | None = None,
    ) -> PipelineResult:
        started = time.perf_counter()
        cfg = self.config
        result = PipelineResult(status="error", question=question, config=cfg.name)
        today = today or date.today()

        tables, concepts, trace = self._link(question, oracle_tables)
        result.trace.append(trace)
        if cfg.gates:
            decision, gate_trace = self._gate(question, tables, concepts, today)
            result.trace.append(gate_trace)
            if decision is not None:
                return self._declined(result, decision, started)
        else:
            result.trace.append(BlockTrace("gates", "skipped", "Tắt trong cấu hình"))
            if not tables:
                ranked = list(self.linker.link(question).scores)
                tables = ranked[:2] or FALLBACK_TABLES
        result.tables = tables

        system, _contexts, conventions, ctx_trace = self._context(question, tables, concepts)
        result.trace.append(ctx_trace)
        result.conventions = [c["id"] for c in conventions]

        user = question
        attempts: list[Attempt] = []
        for round_no in range(cfg.max_repairs + 1 if cfg.verify else 1):
            t0 = time.perf_counter()
            completion = await self.completer.complete(system, user)
            result.prompt_tokens += completion.prompt_tokens
            result.completion_tokens += completion.completion_tokens
            kind, body = parse_reply(completion.text)
            result.trace.append(
                BlockTrace(
                    "generation" if round_no == 0 else "repair",
                    "done"
                    if kind == "SQL"
                    else "declined"
                    if kind in ("ABSTAIN", "CLARIFY")
                    else "failed",
                    f"{kind} ({completion.prompt_tokens}+{completion.completion_tokens} tok)",
                    {"reply": completion.text},
                    _ms(t0),
                )
            )
            if kind in ("ABSTAIN", "CLARIFY") and not attempts:
                parts = [p.strip() for p in body.split("|") if p.strip()]
                decision = GateDecision(
                    kind.lower(), "model", parts[0] if parts else body, tuple(parts[1:])
                )
                return self._declined(result, decision, started)
            if kind != "SQL":
                if attempts:
                    break
                result.message = "Mô hình không trả về SQL hợp lệ"
                result.latency_ms = _ms(started)
                return result

            sql = self.normalise(body.rstrip("; \n"))
            if (blocked := self.guard(sql)) is not None:
                result.trace.append(BlockTrace("guard", "failed", blocked, {"sql": sql}))
                attempts.append(Attempt(sql, blocked, 0, []))
            else:
                result.trace.append(BlockTrace("guard", "done", "Chỉ đọc, một câu SELECT"))
                t1 = time.perf_counter()
                _columns, rows, error = self.execute(sql)
                violations = (
                    [
                        asdict(v)
                        for v in self.assets.registry.verify(sql, question=question, tables=tables)
                    ]
                    if cfg.verify
                    else []
                )
                attempt = Attempt(sql, error, len(rows), violations)
                attempts.append(attempt)
                result.trace.append(
                    BlockTrace(
                        "execute_verify",
                        "failed" if error else "warning" if attempt.problems else "done",
                        "; ".join(attempt.problems) or f"{len(rows)} dòng, không vi phạm quy ước",
                        {"sql": sql, "row_count": len(rows), "violations": violations},
                        _ms(t1),
                    )
                )
                if not attempt.problems or not cfg.verify:
                    break
            if round_no < cfg.max_repairs and cfg.verify:
                user = repair_message(question, attempts[-1].sql, attempts[-1].problems)
                result.repairs += 1

        best = min(attempts, key=lambda a: a.rank()) if attempts else None
        if best is None:
            result.latency_ms = _ms(started)
            return result
        if best.error is None:
            result.columns, result.rows, _ = self.execute(best.sql)
        result.sql = best.sql
        result.violations = best.violations
        if cfg.verify and best.error is None and best.violations:
            # Không trả kết quả vi phạm quy ước đã được chấp nhận: sai im lặng nguy hiểm hơn
            # là không trả lời. SQL vẫn được giữ trong kết quả để người dùng/DE xem.
            ids = ", ".join(v["convention_id"] for v in best.violations)
            decision = GateDecision(
                "abstain",
                "verifier",
                f"SQL vẫn vi phạm quy ước {ids} sau {result.repairs} lần sửa; "
                "hệ thống không trả kết quả chưa tuân thủ.",
            )
            result.rows, result.columns = [], []
            return self._declined(result, decision, started)
        result.row_count = len(result.rows) if best.error is None else 0
        result.status = "error" if best.error else "answered"
        result.message = best.error or ""
        result.latency_ms = _ms(started)
        return result

    def _declined(
        self, result: PipelineResult, decision: GateDecision, started: float
    ) -> PipelineResult:
        result.status = decision.kind
        result.message = decision.message
        result.options = list(decision.options)
        result.latency_ms = _ms(started)
        return result


def _ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)
