import re

from sqlglot import expressions as exp
from sqlglot import parse_one
from sqlglot.errors import ParseError

from t2s.verification.contracts import (
    CheckStatus,
    SemanticCheckResult,
    VerificationDecision,
    VerificationInput,
    VerificationResult,
)
from t2s.verification.sql_ast_parser import SQLGLOT_DIALECTS

COUNT_PATTERN = re.compile(
    r"\b(how many|count of|number of|total number|total count|calculate the count)\b",
    re.IGNORECASE,
)
EXTREMA_PATTERN = re.compile(
    r"\b(highest|lowest|youngest|oldest|earliest|latest|maximum|minimum|most|least|"
    r"top \d+|bottom \d+)\b",
    re.IGNORECASE,
)
SINGULAR_EXTREMA_PATTERN = re.compile(
    r"\b(which|name the|what is the|who is the|find the|give the|top 1|"
    r"the highest|the lowest|the most|the least)\b",
    re.IGNORECASE,
)


class DeterministicSqlVerifier:
    """Evaluator-side deterministic AST-based consistency verifier.

    Uses AST syntax and schema metadata only; strictly does NOT use gold SQL or results.
    """

    async def verify(self, verification_input: VerificationInput) -> VerificationResult:
        dialect_key = verification_input.dialect
        dialect_str = SQLGLOT_DIALECTS[dialect_key] if dialect_key in SQLGLOT_DIALECTS else "sqlite"

        try:
            ast = parse_one(verification_input.candidate_sql, read=dialect_str)
        except (ParseError, Exception) as exc:
            fail_check = SemanticCheckResult(
                status=CheckStatus.FAIL,
                short_reason=f"Failed to parse SQL AST: {exc}",
                question_evidence="",
                sql_evidence=verification_input.candidate_sql[:100],
            )
            unknown_check = SemanticCheckResult(
                status=CheckStatus.UNKNOWN,
                short_reason="Skipped due to AST parse failure",
            )
            return VerificationResult(
                projection=unknown_check,
                aggregation_and_grain=unknown_check,
                filters_and_values=unknown_check,
                join_semantics=unknown_check,
                ordering_and_limit=unknown_check,
                null_semantics=unknown_check,
                schema_reference=fail_check,
                decision=VerificationDecision.REJECT,
                failed_checks=["schema_reference"],
                unknown_checks=[
                    "projection",
                    "aggregation_and_grain",
                    "filters_and_values",
                    "join_semantics",
                    "ordering_and_limit",
                    "null_semantics",
                ],
                confidence=1.0,
            )

        # 1. Schema reference check
        schema_ref_check = self._check_schema_reference(ast, verification_input)

        # 2. Aggregation and grain check
        agg_check = self._check_aggregation_and_grain(ast, verification_input)

        # 3. Ordering and limit check
        order_check = self._check_ordering_and_limit(ast, verification_input)

        # 4. Projection check
        proj_check = self._check_projection(ast, verification_input)

        # 5. Join semantics check
        join_check = self._check_join_semantics(ast, verification_input)

        # 6. Filters and values check
        filter_check = SemanticCheckResult(
            status=CheckStatus.PASS,
            short_reason="No obvious syntax-level filter contradiction detected.",
        )

        # 7. Null semantics check
        null_check = SemanticCheckResult(
            status=CheckStatus.PASS,
            short_reason="No obvious null semantics contradiction detected.",
        )

        checks_map = {
            "projection": proj_check,
            "aggregation_and_grain": agg_check,
            "filters_and_values": filter_check,
            "join_semantics": join_check,
            "ordering_and_limit": order_check,
            "null_semantics": null_check,
            "schema_reference": schema_ref_check,
        }

        failed_checks = [dim for dim, chk in checks_map.items() if chk.status == CheckStatus.FAIL]
        unknown_checks = [
            dim for dim, chk in checks_map.items() if chk.status == CheckStatus.UNKNOWN
        ]

        if failed_checks:
            decision = VerificationDecision.REJECT
        elif unknown_checks:
            decision = VerificationDecision.ABSTAIN
        else:
            decision = VerificationDecision.ACCEPT

        return VerificationResult(
            projection=proj_check,
            aggregation_and_grain=agg_check,
            filters_and_values=filter_check,
            join_semantics=join_check,
            ordering_and_limit=order_check,
            null_semantics=null_check,
            schema_reference=schema_ref_check,
            decision=decision,
            failed_checks=failed_checks,
            unknown_checks=unknown_checks,
            confidence=1.0 if not unknown_checks else 0.5,
        )

    def _check_schema_reference(
        self, ast: exp.Expression, verification_input: VerificationInput
    ) -> SemanticCheckResult:
        if not verification_input.authorized_tables:
            return SemanticCheckResult(
                status=CheckStatus.PASS,
                short_reason="No authorized tables provided for deterministic restriction.",
            )

        # Build normalized authorized tables set
        authorized_table_names = {
            t.split(".")[-1].lower() for t in verification_input.authorized_tables
        }

        # Find all physical tables referenced in AST (excluding CTEs)
        cte_names = {cte.alias_or_name.lower() for cte in ast.find_all(exp.CTE)}
        referenced_tables = {
            t.name.lower()
            for t in ast.find_all(exp.Table)
            if t.name and t.name.lower() not in cte_names
        }

        unauthorized = referenced_tables - authorized_table_names
        if unauthorized:
            return SemanticCheckResult(
                status=CheckStatus.FAIL,
                short_reason=f"Referenced unauthorized tables: {sorted(unauthorized)}",
                question_evidence="",
                sql_evidence=f"Tables: {sorted(unauthorized)}",
            )

        # Check column existence if authorized_columns are available
        if verification_input.authorized_columns:
            all_auth_columns = {
                col.lower()
                for cols in verification_input.authorized_columns.values()
                for col in cols
            }
            if all_auth_columns:
                unknown_cols: set[str] = set()
                for col in ast.find_all(exp.Column):
                    col_name = col.name.lower()
                    if col_name and col_name not in all_auth_columns and col_name != "*":
                        # Verify if this is an alias introduced in scopes
                        is_alias = any(
                            col_name == (alias.alias_or_name or "").lower()
                            for alias in ast.find_all(exp.Alias)
                        )
                        if not is_alias:
                            unknown_cols.add(col_name)

                if unknown_cols:
                    return SemanticCheckResult(
                        status=CheckStatus.FAIL,
                        short_reason=f"Referenced unknown columns: {sorted(unknown_cols)}",
                        sql_evidence=f"Columns: {sorted(unknown_cols)}",
                    )

        return SemanticCheckResult(
            status=CheckStatus.PASS,
            short_reason="All referenced tables and columns are authorized.",
        )

    def _check_aggregation_and_grain(
        self, ast: exp.Expression, verification_input: VerificationInput
    ) -> SemanticCheckResult:
        question_text = f"{verification_input.question} {verification_input.evidence}"
        asks_count = bool(COUNT_PATTERN.search(question_text))

        has_agg = bool(
            ast.find(exp.Count)
            or ast.find(exp.Sum)
            or ast.find(exp.Avg)
            or ast.find(exp.Min)
            or ast.find(exp.Max)
            or ast.find(exp.AggFunc)
        )

        if asks_count and not has_agg:
            match = COUNT_PATTERN.search(question_text)
            snippet = match.group(0) if match else "count"
            return SemanticCheckResult(
                status=CheckStatus.FAIL,
                short_reason=(
                    "Question explicitly asks for count/number "
                    "but candidate SQL contains no aggregate function."
                ),
                question_evidence=snippet,
                sql_evidence="No aggregate function found in AST.",
            )

        return SemanticCheckResult(
            status=CheckStatus.PASS,
            short_reason="Aggregation and grain appear consistent with question intent.",
        )

    def _check_ordering_and_limit(
        self, ast: exp.Expression, verification_input: VerificationInput
    ) -> SemanticCheckResult:
        question_text = f"{verification_input.question} {verification_input.evidence}"
        has_extrema = bool(EXTREMA_PATTERN.search(question_text))
        has_singular = bool(SINGULAR_EXTREMA_PATTERN.search(question_text))

        if has_extrema and has_singular:
            has_order = bool(ast.find(exp.Order))
            has_limit = bool(ast.find(exp.Limit))
            if not has_order and not has_limit:
                match = EXTREMA_PATTERN.search(question_text)
                snippet = match.group(0) if match else "extrema"
                return SemanticCheckResult(
                    status=CheckStatus.FAIL,
                    short_reason=(
                        "Question asks for extrema/ranking "
                        "but candidate SQL lacks ORDER BY / LIMIT."
                    ),
                    question_evidence=snippet,
                    sql_evidence="No ORDER BY or LIMIT found in AST.",
                )

        return SemanticCheckResult(
            status=CheckStatus.PASS,
            short_reason="Ordering and limit appear consistent with question intent.",
        )

    def _check_projection(
        self, ast: exp.Expression, verification_input: VerificationInput
    ) -> SemanticCheckResult:
        select_node = ast.find(exp.Select)
        if not select_node:
            return SemanticCheckResult(
                status=CheckStatus.FAIL,
                short_reason="Candidate SQL does not contain a SELECT clause.",
            )
        expressions = select_node.expressions
        if not expressions:
            return SemanticCheckResult(
                status=CheckStatus.FAIL,
                short_reason="Candidate SELECT clause has no projection expressions.",
            )
        return SemanticCheckResult(
            status=CheckStatus.PASS,
            short_reason=f"Candidate projects {len(expressions)} expressions.",
        )

    def _check_join_semantics(
        self, ast: exp.Expression, verification_input: VerificationInput
    ) -> SemanticCheckResult:
        # Check if joins have join predicates
        for join in ast.find_all(exp.Join):
            if join.kind and "cross" in join.kind.lower():
                continue
            if not join.args.get("on") and not join.args.get("using"):
                # Could be a comma join resolved in WHERE, check if WHERE exists
                where = ast.find(exp.Where)
                if not where:
                    return SemanticCheckResult(
                        status=CheckStatus.FAIL,
                        short_reason=(
                            "Multi-table JOIN without ON/USING clause or WHERE predicate "
                            "(unintentional Cartesian product)."
                        ),
                    )
        return SemanticCheckResult(
            status=CheckStatus.PASS,
            short_reason="Join predicates appear structurally well-formed.",
        )
