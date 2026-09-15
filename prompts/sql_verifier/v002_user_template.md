Question:
<user_question>
{question}
</user_question>

Evidence / Domain Knowledge:
<evidence>
{evidence}
</evidence>

Target Dialect:
{target_dialect}

Authorized Schema & Relationships:
<authorized_schema>
{authorized_schema}
</authorized_schema>

Candidate SQL to Verify:
<candidate_sql>
{candidate_sql}
</candidate_sql>

Perform an independent evaluation of each of the 7 dimensions:
- projection
- aggregation_and_grain
- filters_and_values (strictly check completeness, no hallucinated predicates, literal fidelity, operators, inclusive/exclusive boundaries, string semantics, temporal constraints, category encodings, and AND/OR grouping)
- join_semantics
- ordering_and_limit
- null_semantics
- schema_reference

Return a structured VerificationResult with your decision (ACCEPT, REJECT, or ABSTAIN), failed_checks, unknown_checks, and per-check status, short_reason, question_evidence, and sql_evidence.
