Question:
<user_question>
{question}
</user_question>

Business evidence:
<evidence>
{evidence}
</evidence>

Locale:
{locale}

Target hint:
{target_hint}

Target dialect:
{target_dialect}

Authorized schema:
<authorized_schema>
{authorized_schema}
</authorized_schema>

Glossary:
{glossary_hits}

Grounded values observed in the database:
{value_bindings}

Validated examples:
{validated_examples}

Known unresolved grounding issues:
{unresolved}

Return a structured SqlCandidate with:
- sql
- dialect
- referenced_tables
- referenced_columns
- expected_columns
- assumptions: Working choices, interpretations, caveats, tie-breaking choices, NULL handling choices, formatting assumptions, or other decisions that still allow SQL to be written.
- unresolved: Only information gaps or ambiguities that make it impossible to formulate a defensible executable SQL query from the supplied question and grounded schema.

Contract instructions:
If you can produce a defensible executable SQL query, unresolved MUST be [].
Do not put ordinary assumptions, caveats, tie-breaking notes, NULL-handling notes, duplicate-row notes, or formatting observations in unresolved.
Place those in assumptions instead.
Populate unresolved only when a hard blocker prevents SQL formulation.
