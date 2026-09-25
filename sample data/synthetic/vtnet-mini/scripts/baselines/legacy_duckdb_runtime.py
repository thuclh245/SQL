"""Baseline B0: DuckDBRuntime của backend, đóng băng nguyên văn từ commit 8301397.

Giữ lại CHỈ để tái lập hàng B0 trong ablation (run_ablation.py). Không dùng trong
sản phẩm: backend đã chuyển sang t2s.verified_context. Các lỗi đã biết của bản này
(rule 6 WHERE→HAVING bắt nhầm subquery, rule 8 CAST date_hour, prompt ghi mọi cột
số là VARCHAR, chọn bảng theo tên) được giữ nguyên có chủ đích.
"""
# ruff: noqa
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

from t2s.configuration.settings import Settings

BASE_DIR = Path(__file__).resolve().parents[5]


def format_sql(sql: str, dialect: str = "duckdb") -> str:
    """Format and pretty-print SQL with proper line breaks and indentation."""
    if not sql or not sql.strip():
        return sql
    try:
        import sqlglot
        return sqlglot.transpile(sql.strip(), read=dialect, write=dialect, pretty=True)[0]
    except Exception:
        return sql.strip()



class DuckDBRuntime:
    """Runtime thực thi DuckDB (VTNet Mini) qua sinh câu lệnh LLM & Self-Healing."""

    def __init__(self, db_path: Path, effective_model: str, settings: Settings) -> None:
        self.db_path = db_path
        self.effective_model = effective_model
        self.settings = settings
        self.is_duckdb = True
        self.table_map: dict[str, str] = {}
        self.table_cols: dict[str, dict[str, str]] = {}
        self._load_metadata()

    def _load_metadata(self) -> None:
        
        gen_dir = BASE_DIR / "sample data" / "synthetic" / "vtnet-mini" / "generated"
        mapping_file = gen_dir / "table_name_mapping.json"
        if mapping_file.exists():
            try:
                with open(mapping_file, encoding="utf-8") as f:
                    mapping_data = json.load(f)
                for m in mapping_data:
                    duck_tbl = m.get("duckdb_table", "")
                    if duck_tbl:
                        self.table_map[duck_tbl.lower()] = duck_tbl
                        if "table_name" in m:
                            self.table_map[m["table_name"].lower()] = duck_tbl
                        if "trino_fqn" in m:
                            self.table_map[m["trino_fqn"].lower()] = duck_tbl
                        if "schema" in m and "table_name" in m:
                            s_name = m["schema"]
                            t_name = m["table_name"]
                            self.table_map[f"{s_name}.{t_name}".lower()] = duck_tbl
            except Exception:
                pass

        if self.db_path.exists():
            try:
                import duckdb

                con = duckdb.connect(str(self.db_path), read_only=True)
                for tbl_row in con.execute("SHOW TABLES").fetchall():
                    tbl_name = tbl_row[0]
                    cols_info = con.execute(f"PRAGMA table_info('{tbl_name}')").fetchall()
                    self.table_cols[tbl_name] = {c[1].lower(): c[2].upper() for c in cols_info}
                con.close()
            except Exception:
                pass

    def _get_relevant_schema_context(self, question: str) -> str:
        q_words = set(re.findall(r"\w+", question.lower()))
        scores: list[tuple[int, str]] = []
        key_dims = {
            "date_hour",
            "dt",
            "province_code",
            "area_code",
            "object_id",
            "station_code",
            "hostname",
            "username",
            "region",
            "level_important",
        }

        for tbl, cols in self.table_cols.items():
            score = 0
            tbl_parts = tbl.lower().split("__")
            short_tbl = tbl_parts[-1] if tbl_parts else ""
            schema_name = tbl_parts[-2] if len(tbl_parts) > 1 else ""

            for w in q_words:
                if len(w) < 3:
                    continue
                if w == short_tbl:
                    score += 60
                elif w == schema_name:
                    score += 30
                elif w in tbl.lower():
                    score += 15

            for w in q_words:
                if len(w) < 3:
                    continue
                if any(w in c for c in cols):
                    score += 5
            scores.append((score, tbl))

        scores.sort(reverse=True)
        max_score = scores[0][0] if scores else 0
        threshold = max(20, int(max_score * 0.35)) if max_score >= 30 else 1
        top_tables = [t for s, t in scores if s >= threshold][:3]
        if not top_tables:
            top_tables = [t for s, t in scores[:2] if s > 0]
        if not top_tables:
            top_tables = [
                "hive__aaa__authentication",
                "hive__npms__kpi_access5g_5g_cell_peak_view",
            ]

        lines = []
        for t in top_tables:
            all_cols = list(self.table_cols.get(t, {}).keys())
            ranked_cols: list[tuple[int, str]] = []
            q_lower = question.lower()
            for c in all_cols:
                c_score = 0
                if c in key_dims:
                    c_score += 20
                if c in q_lower:
                    c_score += 80
                for w in q_words:
                    if len(w) >= 3 and w in c:
                        c_score += 5
                ranked_cols.append((c_score, c))
            ranked_cols.sort(reverse=True)
            chosen_cols = [c for _, c in ranked_cols[:25]]
            lines.append(f"- Bảng {t}: [{', '.join(chosen_cols)}]")
        return "\n".join(lines)

    def _rewrite_sql(self, raw_sql: str) -> tuple[str, list[str]]:
        import sqlglot
        from sqlglot import exp

        raw_sql = raw_sql.strip()
        try:
            statements = [s for s in sqlglot.parse(raw_sql, dialect="duckdb") if s is not None]
        except Exception:
            return raw_sql, []

        if not statements:
            return raw_sql, []

        select_stmts = [s for s in statements if isinstance(s, exp.Select)]
        tree = select_stmts[-1] if select_stmts else statements[-1]

        # 1. Chuẩn hóa tên bảng theo DuckDB (loại bỏ dot notation / schema trino)
        current_tables: list[str] = []
        for tbl in tree.find_all(exp.Table):
            parts = []
            if tbl.catalog:
                parts.append(tbl.catalog)
            if tbl.db:
                parts.append(tbl.db)
            if tbl.name:
                parts.append(tbl.name)
            ref_key = ".".join(parts).lower()
            short_key = tbl.name.lower() if tbl.name else ""

            target_name = self.table_map.get(ref_key) or self.table_map.get(short_key)
            if target_name:
                tbl.set("this", exp.to_identifier(target_name))
                tbl.set("db", None)
                tbl.set("catalog", None)
                if target_name not in current_tables:
                    current_tables.append(target_name)
            elif tbl.name and tbl.name not in current_tables:
                current_tables.append(tbl.name)

        # 2. Tập hợp các cột VARCHAR của các bảng được tham chiếu
        varchar_cols: set[str] = set()
        for t in current_tables:
            if t in self.table_cols:
                for cname, ctype in self.table_cols[t].items():
                    if "VARCHAR" in ctype or "CHAR" in ctype or "TEXT" in ctype:
                        varchar_cols.add(cname)

        # 3. Tự động ép kiểu TRY_CAST khi so sánh số với cột VARCHAR
        for cmp_node in tree.find_all(exp.Binary):
            if isinstance(cmp_node, (exp.GT, exp.GTE, exp.LT, exp.LTE, exp.EQ, exp.NEQ)):
                left, right = cmp_node.left, cmp_node.right
                if (
                    isinstance(left, exp.Column)
                    and left.name.lower() in varchar_cols
                    and isinstance(right, exp.Literal)
                    and right.is_number
                ):
                    cast_type = "DOUBLE" if "." in right.this else "BIGINT"
                    left_sql = left.sql(dialect="duckdb")
                    cmp_node.set(
                        "this", sqlglot.parse_one(f"TRY_CAST({left_sql} AS {cast_type})")
                    )
                elif (
                    isinstance(right, exp.Column)
                    and right.name.lower() in varchar_cols
                    and isinstance(left, exp.Literal)
                    and left.is_number
                ):
                    cast_type = "DOUBLE" if "." in left.this else "BIGINT"
                    right_sql = right.sql(dialect="duckdb")
                    cmp_node.set(
                        "expression",
                        sqlglot.parse_one(f"TRY_CAST({right_sql} AS {cast_type})"),
                    )

        # 4. Tự động ép kiểu TRY_CAST trong hàm tổng hợp (SUM, AVG)
        for agg in tree.find_all(exp.AggFunc):
            if isinstance(agg, (exp.Sum, exp.Avg)):
                arg = agg.this
                if isinstance(arg, exp.Column) and arg.name.lower() in varchar_cols:
                    arg_sql = arg.sql(dialect="duckdb")
                    agg.set("this", sqlglot.parse_one(f"TRY_CAST({arg_sql} AS DOUBLE)"))

        # 5. Tự động ép kiểu trong BETWEEN
        for b_node in tree.find_all(exp.Between):
            b_target = b_node.this
            if isinstance(b_target, exp.Column) and b_target.name.lower() in varchar_cols:
                low = b_node.args.get("low")
                if isinstance(low, exp.Literal) and low.is_number:
                    t_sql = b_target.sql(dialect="duckdb")
                    b_node.set("this", sqlglot.parse_one(f"TRY_CAST({t_sql} AS DOUBLE)"))

        # 6. Tự động chuyển điều kiện hàm tổng hợp (AggFunc) trong WHERE sang HAVING
        for sel in tree.find_all(exp.Select):
            where = sel.args.get("where")
            if where and list(where.find_all(exp.AggFunc)):
                conds: list[Any] = []

                def collect_conds(node: Any, acc: list[Any]) -> None:
                    if isinstance(node, exp.And):
                        collect_conds(node.this, acc)
                        collect_conds(node.expression, acc)
                    else:
                        acc.append(node)

                collect_conds(where.this, conds)
                where_conds = [c for c in conds if not list(c.find_all(exp.AggFunc))]
                having_conds = [c for c in conds if list(c.find_all(exp.AggFunc))]

                if where_conds:
                    new_where = where_conds[0]
                    for c in where_conds[1:]:
                        new_where = exp.And(this=new_where, expression=c)
                    sel.set("where", exp.Where(this=new_where))
                else:
                    sel.set("where", None)

                if having_conds:
                    existing_having = sel.args.get("having")
                    all_having = ([existing_having.this] if existing_having else []) + having_conds
                    new_having = all_having[0]
                    for c in all_having[1:]:
                        new_having = exp.And(this=new_having, expression=c)
                    sel.set("having", exp.Having(this=new_having))

        # 7. Tự động ép kiểu ngày tháng khi trừ INTERVAL (-(VARCHAR, INTERVAL))
        for sub in tree.find_all(exp.Sub):
            if isinstance(sub.expression, exp.Interval):
                target = sub.this
                target_sql = target.sql(dialect="duckdb")
                sub.set("this", sqlglot.parse_one(f"TRY_CAST({target_sql} AS DATE)"))

        # 8. Tự động ép kiểu TRY_CAST(... AS DATE) cho cột ngày khi so sánh với biểu thức ngày/tháng
        for comp in tree.find_all(exp.Binary):
            if isinstance(comp, (exp.GTE, exp.LTE, exp.GT, exp.LT)):
                for side in ("this", "expression"):
                    node = getattr(comp, side, None)
                    is_date_col = (
                        isinstance(node, exp.Column)
                        and node.name.lower() in ("date_hour", "dt", "date", "ngay")
                    )
                    if is_date_col:
                        col_sql = node.sql(dialect="duckdb")
                        comp.set(side, sqlglot.parse_one(f"TRY_CAST({col_sql} AS DATE)"))

        clean_sql = tree.sql(dialect="duckdb")
        return clean_sql, current_tables

    async def run_pipeline(self, question: str, evidence: list[str]) -> dict[str, Any]:
        import duckdb
        import httpx

        candidate_sql = ""
        try:
            provider_url = (
                os.getenv("VLLM_BASE_URL")
                or self.settings.vllm_base_url
                or "https://openrouter.ai/api/v1"
            )
            api_key = os.getenv("LLM_API_KEY") or self.settings.llm_api_key or ""
            schema_hint = self._get_relevant_schema_context(question)

            sys_prompt = (
                "Bạn là chuyên gia Text-to-SQL cho hệ CSDL DuckDB viễn thông VTNet.\n"
                "LƯỢC ĐỒ CSDL LIÊN QUAN:\n"
                f"{schema_hint}\n\n"
                "QUY TẮC BẮT BUỘC:\n"
                "1. Chỉ trả về DUY NHẤT 1 câu lệnh SELECT (không sinh nhiều câu lệnh).\n"
                "2. Các cột số dạng VARCHAR. BẮT BUỘC dùng TRY_CAST(cột AS BIGINT) hoặc "
                "TRY_CAST(cột AS DOUBLE) khi so sánh hoặc tính toán (accept, reject, v.v.).\n"
                "3. Khi JOIN các bảng/CTE có chung tên cột (như province_code, area_code), "
                "BẮT BUỘC ghi rõ alias bảng (ví dụ: pc.province_code, pc.area_code) ở SELECT, "
                "GROUP BY và GROUPING SETS để tránh lỗi Ambiguous reference.\n"
                "4. Trả về SQL thuần (không markdown code block, không giải thích)."
            )
            user_content = question
            if evidence:
                user_content += f"\nGợi ý: {' '.join(evidence)}"

            headers = {"Content-Type": "application/json"}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

            payload = {
                "model": self.effective_model,
                "messages": [
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": user_content},
                ],
                "temperature": 0.0,
                "max_tokens": 4096,
            }
            async with httpx.AsyncClient(timeout=45.0) as client:
                resp = await client.post(
                    f"{provider_url.rstrip('/')}/chat/completions",
                    json=payload,
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()
                msg = data["choices"][0]["message"]
                raw_text = msg.get("content") or msg.get("reasoning") or ""
                candidate_sql = raw_text.strip()
                if "```" in candidate_sql:
                    # Trích xuất khối sql bên trong markdown nếu có
                    code_match = re.search(r"```(?:sql)?\s*([\s\S]*?)```", candidate_sql)
                    if code_match:
                        candidate_sql = code_match.group(1).strip()
                    else:
                        candidate_sql = re.sub(r"^```(?:sql)?\n?", "", candidate_sql)
                        candidate_sql = re.sub(r"\n?```$", "", candidate_sql).strip()

                usage_data = data.get("usage") or {}
                prompt_tokens = usage_data.get("prompt_tokens") or 0
                completion_tokens = usage_data.get("completion_tokens") or 0
                total_tokens = usage_data.get("total_tokens") or (prompt_tokens + completion_tokens)
                token_usage = {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens,
                }
        except Exception as e:
            fallback_tokens = {
                "prompt_tokens": len(question.split()) * 4,
                "completion_tokens": 0,
                "total_tokens": len(question.split()) * 4,
            }
            return {
                "status": "FAILED",
                "candidate_sql": "",
                "ast_tables": [],
                "columns": [],
                "rows": [],
                "row_count": 0,
                "token_usage": fallback_tokens,
                "prompt_tokens": fallback_tokens["prompt_tokens"],
                "completion_tokens": fallback_tokens["completion_tokens"],
                "total_tokens": fallback_tokens["total_tokens"],
                "execution_time_ms": 1,
                "error_message": f"Gặp lỗi khi gọi LLM sinh câu lệnh SQL: {str(e)}",
                "is_execution_failed": True,
            }

        # Áp dụng rewrite & auto-cast
        clean_sql, ast_tables = self._rewrite_sql(candidate_sql)

        # Thực thi với cơ chế tự phục hồi (Self-Healing)
        start_t = time.perf_counter()
        exec_err: Exception | None = None
        for attempt in range(5):
            try:
                con = duckdb.connect(str(self.db_path), read_only=True)
                cur = con.cursor()
                cur.execute(clean_sql)
                columns = [desc[0] for desc in cur.description] if cur.description else []
                rows = [list(r) for r in cur.fetchmany(100)]
                con.close()
                exec_time_ms = max(1, int((time.perf_counter() - start_t) * 1000))

                return {
                    "status": "SUCCESS",
                    "candidate_sql": format_sql(clean_sql, "duckdb"),
                    "ast_tables": ast_tables,
                    "columns": columns,
                    "rows": rows,
                    "row_count": len(rows),
                    "token_usage": token_usage,
                    "prompt_tokens": token_usage["prompt_tokens"],
                    "completion_tokens": token_usage["completion_tokens"],
                    "total_tokens": token_usage["total_tokens"],
                    "execution_time_ms": exec_time_ms,
                    "error_message": None,
                    "is_execution_failed": False,
                }
            except Exception as e:
                exec_err = e
                err_msg = str(e)
                # Self-healing attempt: Lỗi tham chiếu mơ hồ cột (Ambiguous reference)
                amb_pat = r"Ambiguous reference to column name \"(\w+)\" \(use: \"([^\"]+)\""
                m_amb = re.search(amb_pat, err_msg)
                if m_amb:
                    col_name, suggested = m_amb.group(1), m_amb.group(2)
                    alias = suggested.split(".")[0]
                    try:
                        import sqlglot
                        from sqlglot import exp

                        tree_amb = sqlglot.parse_one(clean_sql, dialect="duckdb")
                        for col_node in tree_amb.find_all(exp.Column):
                            if col_node.find_ancestor(exp.With):
                                continue
                            if col_node.name.lower() == col_name.lower() and not col_node.table:
                                col_node.set("table", exp.to_identifier(alias))
                        clean_sql = tree_amb.sql(dialect="duckdb")
                        continue
                    except Exception:
                        pass

                # Self-healing attempt: Lỗi so sánh VARCHAR vs INTEGER/DOUBLE
                if attempt == 0 and "Cannot compare values of type VARCHAR and type" in err_msg:
                    clean_sql = re.sub(
                        r"(\b\w+\b)\s*([><=]+)\s*(\d+(?:\.\d+)?)",
                        r"TRY_CAST(\1 AS DOUBLE) \2 \3",
                        clean_sql,
                    )
                    continue
                # Self-healing attempt: Lỗi trừ INTERVAL trên VARCHAR
                interval_err = (
                    "No function matches the given name and argument types "
                    "'-(VARCHAR, INTERVAL)'"
                )
                if attempt == 0 and interval_err in err_msg:
                    clean_sql = re.sub(
                        r"(\([^\)]*max_dt[^\)]*\)|\bmax_dt\b|\bdate_hour\b)\s*-\s*INTERVAL",
                        r"TRY_CAST(\1 AS DATE) - INTERVAL",
                        clean_sql,
                    )
                    continue
                # Self-healing attempt: Cột date thay vì ngay hoặc date_hour
                if attempt == 0 and 'Referenced column "date" not found' in err_msg:
                    if any("date_hour" in self.table_cols.get(t, {}) for t in ast_tables):
                        clean_sql = re.sub(r"\bdate\b", "date_hour", clean_sql)
                        continue
                    if any("ngay" in self.table_cols.get(t, {}) for t in ast_tables):
                        clean_sql = re.sub(r"\bdate\b", "ngay", clean_sql)
                        continue
                break

        exec_time_ms = max(1, int((time.perf_counter() - start_t) * 1000))
        return {
            "status": "EXECUTION_ERROR",
            "candidate_sql": format_sql(clean_sql, "duckdb"),
            "ast_tables": ast_tables,
            "columns": [],
            "rows": [],
            "row_count": 0,
            "token_usage": token_usage,
            "prompt_tokens": token_usage["prompt_tokens"],
            "completion_tokens": token_usage["completion_tokens"],
            "total_tokens": token_usage["total_tokens"],
            "execution_time_ms": exec_time_ms,
            "error_message": str(exec_err) if exec_err else "Lỗi thực thi",
            "is_execution_failed": True,
        }


