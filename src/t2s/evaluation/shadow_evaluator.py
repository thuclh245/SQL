"""Shadow evaluation engine for rejected P5 candidates.

Evaluates UNRESOLVED candidates offline after runtime decision STOP.
Never alters runtime behavior or feeds results back into the runtime.
Preserves all P1 security boundaries: AST parse, read-only validation, table access authorization.
"""

import sqlite3
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from sqlglot import exp

from t2s.benchmark.case_loader import BenchmarkCaseBundle
from t2s.benchmark.catalog_loader import load_bird_catalog_tables
from t2s.benchmark.scoring import execute_gold_sql, score_execution_accuracy
from t2s.errors import UnsafeSqlError
from t2s.verification.sql_ast_parser import SqlAstParser
from t2s.verification.sql_safety_validator import SqlSafetyValidator


class ShadowEvaluationStatus(StrEnum):
    """Diagnostic status for a shadow-evaluated rejected candidate."""

    SHADOW_CORRECT = "SHADOW_CORRECT"
    SHADOW_INCORRECT = "SHADOW_INCORRECT"
    SHADOW_EXECUTION_ERROR = "SHADOW_EXECUTION_ERROR"
    SHADOW_SAFETY_REJECTED = "SHADOW_SAFETY_REJECTED"
    SHADOW_ACCESS_REJECTED = "SHADOW_ACCESS_REJECTED"
    CANDIDATE_UNAVAILABLE = "CANDIDATE_UNAVAILABLE"


class UnresolvedNoteCategory(StrEnum):
    """Categorization of solver unresolved commentary / assumptions."""

    HARD_BLOCKER = "HARD_BLOCKER"
    SOFT_ASSUMPTION = "SOFT_ASSUMPTION"
    SOFT_CAVEAT = "SOFT_CAVEAT"
    TIE_BREAK_NOTE = "TIE_BREAK_NOTE"
    DATA_SEMANTIC_UNCERTAINTY = "DATA_SEMANTIC_UNCERTAINTY"
    SCHEMA_UNCERTAINTY = "SCHEMA_UNCERTAINTY"
    OTHER = "OTHER"


def classify_unresolved_note(note: str) -> UnresolvedNoteCategory:
    """Deterministically classify a single unresolved note string."""
    text = note.strip().lower()

    # 1. Hard blocker signals: impossible to write query, completely missing essential data
    if any(
        phrase in text
        for phrase in [
            "cannot be",
            "not possible",
            "impossible",
            "no column or table",
            "no telephone",
            "no phone",
            "cannot reliably correlate",
            "cannot be determined",
            "cannot be returned",
            "not possible to restrict",
            "not possible to filter",
            "cannot be applied",
            "missing required table",
            "does not exist in the database",
            "no relationship or join key",
            "no patient-level join key",
            "no 'city' or 'place' column",
            "has no time/timestamp column",
            "no date or year column",
            "not present in the authorized schema, so the criterion",
            "cannot reliably determine",
            "without a way to join",
            "missing join between",
            "no such tables/columns exist",
            "cannot show card names",
            "cannot be constructed against the provided schema",
            "specific customer or transaction at 16:25:00 was not provided",
        ]
    ):
        return UnresolvedNoteCategory.HARD_BLOCKER

    # 2. Tie-breaking signals
    if any(
        phrase in text
        for phrase in [
            "tie",
            "tie-break",
            "tie-breaker",
            "ties",
            "sort position",
            "order by",
            "limit 1",
            "relative order",
            "arbitrary top row",
            "ordering will be lexicographic",
            "simple desc ordering",
        ]
    ):
        return UnresolvedNoteCategory.TIE_BREAK_NOTE

    # 3. Schema uncertainty: column/table ambiguity, multiple candidates, which column to choose
    if any(
        phrase in text
        for phrase in [
            "foreign key",
            "relationship",
            "join condition",
            "unqualified table",
            "which table",
            "which column",
            "which single column",
            "different column or table",
            "order.k_symbol (or another table)",
            "diagnosis columns in both",
            "both patient and examination",
            "prefer frpm",
            "cards.asciiname",
            "foreign_data.name",
            "using account.date as the approval date",
            "no explicit 'name' column",
            "no explicit relationship in the schema",
            "no disposition/ownership table",
            "without that mapping",
            "whether 'premium' refers to segments in the customers table rather than gasstations",
            "without a mapping to sets.code",
            "no documented relationship or column links",
            "table structure",
        ]
    ):
        return UnresolvedNoteCategory.SCHEMA_UNCERTAINTY

    # 4. Data semantic uncertainty: value encoding, case sensitivity, format, codes, date formatting
    if any(
        phrase in text
        for phrase in [
            "exact format",
            "format of",
            "exact stored string",
            "stored value",
            "casing",
            "format",
            "spelling",
            "code value",
            "filter value",
            "synonyms",
            "values or code",
            "doctype or doc",
            "parseable by strftime",
            "type text",
            "delimiters",
            "characters",
            "case-insensitive",
            "whitespace",
            "string/format",
            "timezone",
            "misspelling",
            "isstorylight",
            "actually exist",
            "admission = '-'",
            "county naming could differ",
            "if approved uses values other than",
        ]
    ):
        return UnresolvedNoteCategory.DATA_SEMANTIC_UNCERTAINTY

    # 5. Soft assumption signals: interpretive choices made by the model
    if any(
        phrase in text
        for phrase in [
            "assumed",
            "assume",
            "assumption",
            "interpreted",
            "interpretation",
            "best guess",
            "chosen interpretation",
            "unclear if the user intended",
            "i assumed",
            "i chose",
            "i used",
            "this query follows",
            "query uses individual loan amounts",
            "the query uses all years",
            "query implements average",
            "this query computes",
            "this query uses total cards",
            "this query counts total races",
            "this query uses simple row counts",
            "query uses exact",
            "query uses substr",
            "query counts rows matching",
            "treating",
        ]
    ):
        return UnresolvedNoteCategory.SOFT_ASSUMPTION

    # 6. Soft caveat signals: nulls, duplicates, distinct, join exclusions, zero-row edge cases
    if any(
        phrase in text
        for phrase in [
            "null",
            "missing rows",
            "duplicate",
            "duplicates",
            "distinct",
            "empty rows",
            "outer join",
            "excluded by",
            "inner join",
            "left join",
            "if multiple",
            "behavior for nulls",
            "behavior when",
            "unclear whether you wanted",
            "deduplicate",
            "will return no rows",
            "may return no rows",
            "absence of rows",
            "may not exist",
            "if the user record was deleted",
            "could imply an additional filter",
        ]
    ):
        return UnresolvedNoteCategory.SOFT_CAVEAT

    return UnresolvedNoteCategory.OTHER


@dataclass(frozen=True)
class ShadowCaseResult:
    """Diagnostic outcome for a single unresolved case."""

    case_id: str
    db_id: str
    status: ShadowEvaluationStatus
    candidate_sql: str | None = None
    ast_valid: bool | None = None
    safety_valid: bool | None = None
    authorization_valid: bool | None = None
    execution_success: bool | None = None
    execution_error: str | None = None
    matches_gold: bool | None = None
    unresolved_notes: list[str] = field(default_factory=list)
    classified_notes: list[tuple[UnresolvedNoteCategory, str]] = field(
        default_factory=list
    )
    details: str | None = None


class ShadowEvaluator:
    """Evaluates rejected SQL candidates offline with strict read-only safety."""

    def __init__(
        self,
        database_root: Path,
        safety_validator: SqlSafetyValidator | None = None,
        statement_timeout_seconds: int = 30,
    ) -> None:
        self.database_root = database_root
        self.safety_validator = safety_validator or SqlSafetyValidator()
        self.ast_parser = SqlAstParser()
        self.statement_timeout_seconds = statement_timeout_seconds

    def evaluate_case(
        self,
        case_id: str,
        db_id: str,
        candidate_sql: str | None,
        gold_sql: str,
        authorized_tables: set[str] | None = None,
        unresolved_notes: list[str] | None = None,
    ) -> ShadowCaseResult:
        """Evaluate a rejected candidate offline against gold execution."""
        notes = unresolved_notes or []
        classified = [(classify_unresolved_note(n), n) for n in notes]

        if not candidate_sql or not candidate_sql.strip():
            return ShadowCaseResult(
                case_id=case_id,
                db_id=db_id,
                status=ShadowEvaluationStatus.CANDIDATE_UNAVAILABLE,
                candidate_sql=None,
                unresolved_notes=notes,
                classified_notes=classified,
                details="Candidate SQL was not recorded or is empty.",
            )

        # 1. AST Parse & Safety Validation
        try:
            parsed_sql = self.ast_parser.parse_single_statement(
                sql=candidate_sql, dialect="sqlite"
            )
            self.safety_validator.validate_read_only_sql(parsed_sql)
        except UnsafeSqlError as exc:
            # Check if parse failed or safety rejected
            err_msg = str(exc)
            if "could not be parsed" in err_msg or "exactly one statement" in err_msg:
                return ShadowCaseResult(
                    case_id=case_id,
                    db_id=db_id,
                    status=ShadowEvaluationStatus.SHADOW_EXECUTION_ERROR,
                    candidate_sql=candidate_sql,
                    ast_valid=False,
                    unresolved_notes=notes,
                    classified_notes=classified,
                    details=f"AST parse error: {exc}",
                )
            return ShadowCaseResult(
                case_id=case_id,
                db_id=db_id,
                status=ShadowEvaluationStatus.SHADOW_SAFETY_REJECTED,
                candidate_sql=candidate_sql,
                ast_valid=True,
                safety_valid=False,
                unresolved_notes=notes,
                classified_notes=classified,
                details=f"Safety check rejected: {exc}",
            )
        except Exception as exc:
            return ShadowCaseResult(
                case_id=case_id,
                db_id=db_id,
                status=ShadowEvaluationStatus.SHADOW_EXECUTION_ERROR,
                candidate_sql=candidate_sql,
                ast_valid=False,
                unresolved_notes=notes,
                classified_notes=classified,
                details=f"AST error: {exc}",
            )

        # 2. Authorization Validation (Tables must be authorized)
        if authorized_tables is not None:
            try:
                referenced_tables = parsed_sql.referenced_table_identifiers()
            except Exception:
                referenced_tables = {
                    t.name.lower() for t in parsed_sql.ast.find_all(exp.Table)
                }
            normalized_authorized = {
                t.split(".")[-1].lower() for t in authorized_tables
            }
            unauthorized = {
                t.split(".")[-1].lower() for t in referenced_tables
            } - normalized_authorized
            if unauthorized:
                return ShadowCaseResult(
                    case_id=case_id,
                    db_id=db_id,
                    status=ShadowEvaluationStatus.SHADOW_ACCESS_REJECTED,
                    candidate_sql=candidate_sql,
                    ast_valid=True,
                    safety_valid=True,
                    authorization_valid=False,
                    unresolved_notes=notes,
                    classified_notes=classified,
                    details=f"Unauthorized tables: {unauthorized}",
                )

        # 4. Read-Only Execution on Database
        db_path = self.database_root / db_id / f"{db_id}.sqlite"
        if not db_path.exists():
            return ShadowCaseResult(
                case_id=case_id,
                db_id=db_id,
                status=ShadowEvaluationStatus.SHADOW_EXECUTION_ERROR,
                candidate_sql=candidate_sql,
                ast_valid=True,
                safety_valid=True,
                authorization_valid=True,
                execution_success=False,
                unresolved_notes=notes,
                classified_notes=classified,
                details=f"Database file not found: {db_path}",
            )

        exec_ok, candidate_rows, exec_err = self._execute_readonly(
            candidate_sql, db_path
        )
        if not exec_ok:
            return ShadowCaseResult(
                case_id=case_id,
                db_id=db_id,
                status=ShadowEvaluationStatus.SHADOW_EXECUTION_ERROR,
                candidate_sql=candidate_sql,
                ast_valid=True,
                safety_valid=True,
                authorization_valid=True,
                execution_success=False,
                execution_error=exec_err,
                unresolved_notes=notes,
                classified_notes=classified,
                details=f"Execution error: {exec_err}",
            )

        # 5. Execute Gold and Compare
        gold_res = execute_gold_sql(gold_sql, db_path)
        if not gold_res.ok:
            return ShadowCaseResult(
                case_id=case_id,
                db_id=db_id,
                status=ShadowEvaluationStatus.SHADOW_EXECUTION_ERROR,
                candidate_sql=candidate_sql,
                ast_valid=True,
                safety_valid=True,
                authorization_valid=True,
                execution_success=True,
                unresolved_notes=notes,
                classified_notes=classified,
                details=f"Gold execution failed: {gold_res.error}",
            )

        matches = score_execution_accuracy(
            generated_rows=candidate_rows,
            gold_rows=gold_res.rows,
            gold_sql=gold_sql,
        )

        status = (
            ShadowEvaluationStatus.SHADOW_CORRECT
            if matches
            else ShadowEvaluationStatus.SHADOW_INCORRECT
        )
        return ShadowCaseResult(
            case_id=case_id,
            db_id=db_id,
            status=status,
            candidate_sql=candidate_sql,
            ast_valid=True,
            safety_valid=True,
            authorization_valid=True,
            execution_success=True,
            matches_gold=matches,
            unresolved_notes=notes,
            classified_notes=classified,
            details="Execution matched gold" if matches else "Semantic mismatch",
        )

    def _execute_readonly(
        self, sql: str, db_path: Path
    ) -> tuple[bool, list[dict[str, Any]], str | None]:
        uri = f"file:{db_path.resolve()}?mode=ro"
        try:
            conn = sqlite3.connect(
                uri, uri=True, timeout=self.statement_timeout_seconds
            )
            try:
                conn.execute("PRAGMA query_only = ON")
                cursor = conn.execute(sql)
                col_names = (
                    [desc[0] for desc in cursor.description]
                    if cursor.description
                    else []
                )
                raw_rows = cursor.fetchall()
                dict_rows = [dict(zip(col_names, row, strict=False)) for row in raw_rows]
                return True, dict_rows, None
            finally:
                conn.close()
        except Exception as exc:
            return False, [], str(exc)


def analyze_grounding_diagnostics(
    cases: list[dict[str, Any]],
    bundles: dict[str, BenchmarkCaseBundle],
    tables_json_path: Path,
) -> dict[str, Any]:
    """Perform evaluator-only diagnostics on gold tables, columns, and relationships."""
    import sqlglot

    catalogs: dict[str, dict[str, set[str]]] = {}
    db_relationships: dict[str, set[frozenset[str]]] = {}

    for b in bundles.values():
        db_id = b.inference_case.db_id
        if db_id not in catalogs:
            tables = load_bird_catalog_tables(db_id, tables_json_path)
            catalogs[db_id] = {
                t.sql_identifier.lower(): {c.column_name.lower() for c in t.columns}
                for t in tables
                if t.sql_identifier is not None
            }
            rel_set: set[frozenset[str]] = set()
            for t in tables:
                for fk in t.foreign_keys:
                    t1 = fk.from_table_fqn.split(".")[-1].lower()
                    t2 = fk.to_table_fqn.split(".")[-1].lower()
                    rel_set.add(frozenset([t1, t2]))
            db_relationships[db_id] = rel_set

    tot_gold_tables = 0
    cov_gold_tables = 0
    full_table_cases = 0

    tot_gold_cols = 0
    cov_gold_cols = 0
    full_col_cases = 0

    multi_table_join_cases = 0
    rel_covered_join_cases = 0

    table_miss_cases: list[dict[str, Any]] = []
    col_miss_cases: list[dict[str, Any]] = []
    rel_miss_cases: list[dict[str, Any]] = []

    for c in cases:
        cid = c["case_id"]
        bundle = bundles[cid]
        gold_sql = bundle.scoring_gold.official_sql
        if not gold_sql:
            continue
        parsed = sqlglot.parse_one(gold_sql, read="sqlite")

        # 1. Tables
        gold_tables = {t.name.lower() for t in parsed.find_all(exp.Table)}
        final_tables = {t.split(".")[-1].lower() for t in c.get("final_tables", [])}
        tot_gold_tables += len(gold_tables)
        cov = gold_tables.intersection(final_tables)
        cov_gold_tables += len(cov)
        if gold_tables.issubset(final_tables):
            full_table_cases += 1
        else:
            table_miss_cases.append(
                {
                    "case_id": cid,
                    "db_id": bundle.inference_case.db_id,
                    "missing_tables": sorted(list(gold_tables - final_tables)),
                }
            )

        # 2. Columns
        db_cat = catalogs[bundle.inference_case.db_id]
        alias_map: dict[str, str] = {}
        for tbl_expr in parsed.find_all(exp.Table):
            t_name = tbl_expr.name.lower()
            alias_map[t_name] = t_name
            if tbl_expr.alias:
                alias_map[tbl_expr.alias.lower()] = t_name

        alias_names = {alias.alias.lower() for alias in parsed.find_all(exp.Alias)}
        gold_physical_cols: set[tuple[str, str]] = set()
        for col in parsed.find_all(exp.Column):
            cname = col.name.lower()
            if cname == "*" or cname in alias_names:
                continue
            t_ref = col.table.lower() if col.table else None
            resolved_t = alias_map.get(t_ref) if t_ref else None

            if resolved_t and resolved_t in db_cat and cname in db_cat[resolved_t]:
                gold_physical_cols.add((resolved_t, cname))
            else:
                candidate_tables = [
                    t for t in alias_map.values() if t in db_cat
                ] or list(db_cat.keys())
                for tname in candidate_tables:
                    if cname in db_cat[tname]:
                        gold_physical_cols.add((tname, cname))
                        break

        tot_gold_cols += len(gold_physical_cols)
        covered_cols = {
            (t, col_n) for (t, col_n) in gold_physical_cols if t in final_tables
        }
        cov_gold_cols += len(covered_cols)
        if gold_physical_cols == covered_cols:
            full_col_cases += 1
        else:
            col_miss_cases.append(
                {
                    "case_id": cid,
                    "db_id": bundle.inference_case.db_id,
                    "missing_columns": [
                        f"{t}.{col_n}"
                        for (t, col_n) in sorted(gold_physical_cols - covered_cols)
                    ],
                }
            )

        # 3. Join / Relationships
        if len(gold_tables) > 1:
            multi_table_join_cases += 1
            rels = db_relationships[bundle.inference_case.db_id]
            has_rel = any(
                frozenset([t1, t2]) in rels
                for t1 in gold_tables
                for t2 in gold_tables
                if t1 != t2
            )
            if has_rel:
                rel_covered_join_cases += 1
            else:
                rel_miss_cases.append(
                    {
                        "case_id": cid,
                        "db_id": bundle.inference_case.db_id,
                        "gold_tables": sorted(list(gold_tables)),
                    }
                )

    return {
        "gold_table_coverage": {
            "covered": cov_gold_tables,
            "total": tot_gold_tables,
            "pct": round(cov_gold_tables / tot_gold_tables * 100, 2)
            if tot_gold_tables
            else 0.0,
            "full_cases": full_table_cases,
            "total_cases": len(cases),
            "missing_cases": table_miss_cases,
        },
        "gold_column_coverage": {
            "covered": cov_gold_cols,
            "total": tot_gold_cols,
            "pct": round(cov_gold_cols / tot_gold_cols * 100, 2)
            if tot_gold_cols
            else 0.0,
            "full_cases": full_col_cases,
            "total_cases": len(cases),
            "missing_cases": col_miss_cases,
        },
        "relationship_evidence_coverage": {
            "covered": rel_covered_join_cases,
            "total": multi_table_join_cases,
            "pct": round(rel_covered_join_cases / multi_table_join_cases * 100, 2)
            if multi_table_join_cases
            else 0.0,
            "missing_cases": rel_miss_cases,
        },
    }


def decompose_error_budget(
    cases: list[dict[str, Any]],
    bundles: dict[str, BenchmarkCaseBundle],
    tables_json_path: Path,
) -> dict[str, Any]:
    """Decompose all benchmark errors into categories A through H with strict precedence."""
    import sqlglot

    catalogs: dict[str, dict[str, set[str]]] = {}
    db_relationships: dict[str, set[frozenset[str]]] = {}

    for b in bundles.values():
        db_id = b.inference_case.db_id
        if db_id not in catalogs:
            tables = load_bird_catalog_tables(db_id, tables_json_path)
            catalogs[db_id] = {
                t.sql_identifier.lower(): {c.column_name.lower() for c in t.columns}
                for t in tables
                if t.sql_identifier is not None
            }
            rel_set: set[frozenset[str]] = set()
            for t in tables:
                for fk in t.foreign_keys:
                    t1 = fk.from_table_fqn.split(".")[-1].lower()
                    t2 = fk.to_table_fqn.split(".")[-1].lower()
                    rel_set.add(frozenset([t1, t2]))
            db_relationships[db_id] = rel_set

    budget: dict[str, list[str]] = {
        "A_GROUNDING_TABLE_MISS": [],
        "B_GROUNDING_COLUMN_MISS": [],
        "C_RELATIONSHIP_EVIDENCE_MISS": [],
        "D_FALSE_POSITIVE_ABSTENTION": [],
        "E_TRUE_POSITIVE_ABSTENTION": [],
        "F_SQL_SEMANTIC_ERROR": [],
        "G_PROVIDER_FAILURE": [],
        "H_SUSPECTED_FALSE_ABSTENTION": [],
    }

    for c in cases:
        cid = c["case_id"]
        bundle = bundles[cid]
        status = c["runtime_status"]
        tax = c["failure_taxonomy"]
        correct = c.get("execution_correct")

        if correct is True:
            continue

        gold_sql = bundle.scoring_gold.official_sql
        if not gold_sql:
            continue
        parsed = sqlglot.parse_one(gold_sql, read="sqlite")
        gold_tables = {t.name.lower() for t in parsed.find_all(exp.Table)}
        final_tables = {t.split(".")[-1].lower() for t in c.get("final_tables", [])}
        db_cat = catalogs[bundle.inference_case.db_id]

        # 1. Provider failure
        if (
            tax == "SQL_GENERATION_ERROR"
            or c.get("error_code") in {"provider_timeout", "generation_failed"}
            or (c.get("error_message") and "OpenAI" in c.get("error_message", ""))
        ):
            budget["G_PROVIDER_FAILURE"].append(cid)
            continue

        # 2. Grounding table miss
        if not gold_tables.issubset(final_tables):
            budget["A_GROUNDING_TABLE_MISS"].append(cid)
            continue

        # 3. Grounding column miss
        alias_map = {}
        for tbl_expr in parsed.find_all(exp.Table):
            t_name = tbl_expr.name.lower()
            alias_map[t_name] = t_name
            if tbl_expr.alias:
                alias_map[tbl_expr.alias.lower()] = t_name

        alias_names = {alias.alias.lower() for alias in parsed.find_all(exp.Alias)}
        gold_physical_cols = set()
        for col in parsed.find_all(exp.Column):
            cname = col.name.lower()
            if cname == "*" or cname in alias_names:
                continue
            t_ref = col.table.lower() if col.table else None
            resolved_t = alias_map.get(t_ref) if t_ref else None

            if resolved_t and resolved_t in db_cat and cname in db_cat[resolved_t]:
                gold_physical_cols.add((resolved_t, cname))
            else:
                candidate_tables = [
                    t for t in alias_map.values() if t in db_cat
                ] or list(db_cat.keys())
                for tname in candidate_tables:
                    if cname in db_cat[tname]:
                        gold_physical_cols.add((tname, cname))
                        break

        if any(tname not in final_tables for tname, _ in gold_physical_cols):
            budget["B_GROUNDING_COLUMN_MISS"].append(cid)
            continue

        # 4. Relationship evidence miss
        if len(gold_tables) > 1:
            rels = db_relationships[bundle.inference_case.db_id]
            has_rel = any(
                frozenset([t1, t2]) in rels
                for t1 in gold_tables
                for t2 in gold_tables
                if t1 != t2
            )
            if not has_rel:
                budget["C_RELATIONSHIP_EVIDENCE_MISS"].append(cid)
                continue

        # 5 & 6: False / True positive abstention
        # Offline verified via candidate execution: 0 in Stage C since candidates were unavailable

        # 7. SQL semantic error
        if status == "SUCCESS" and correct is False:
            budget["F_SQL_SEMANTIC_ERROR"].append(cid)
            continue

        # 8. Suspected false abstention (unresolved cases with grounded tables/columns/rels)
        if status == "UNRESOLVED":
            budget["H_SUSPECTED_FALSE_ABSTENTION"].append(cid)
            continue

    return budget
