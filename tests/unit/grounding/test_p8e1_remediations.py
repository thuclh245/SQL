from t2s.catalog import (
    CatalogColumn,
    CatalogForeignKey,
    CatalogSearchDocumentBuilder,
    CatalogTable,
)
from t2s.catalog.in_memory_catalog import InMemoryCatalog
from t2s.contracts import QueryRequest
from t2s.grounding import (
    GroundingBudget,
    GroundingContextBuilder,
    InMemorySchemaSearch,
    RelationshipExpander,
    SchemaRetriever,
)
from t2s.grounding.retrieval_ranker import RankedTableCandidate
from t2s.security import AuthorizationService, AuthorizedSqlResource, UserIdentity


class SimpleAccessPolicy:
    def __init__(self, allowed_tables: list[CatalogTable]) -> None:
        self.allowed_tables = allowed_tables

    def get_authorized_resources(self, user_identity: UserIdentity) -> list[AuthorizedSqlResource]:
        return [
            AuthorizedSqlResource(
                catalog_fqn=t.table_fqn,
                sql_identifier=t.sql_identifier or t.table_name,
            )
            for t in self.allowed_tables
        ]


def _col(
    table_fqn: str, name: str, data_type: str = "text", is_pk: bool = False, pos: int = 1
) -> CatalogColumn:
    return CatalogColumn(
        column_fqn=f"{table_fqn}.{name}",
        column_name=name,
        data_type=data_type,
        is_primary_key=is_pk,
        ordinal_position=pos,
    )


def test_relationship_expander_incoming_outgoing_and_composite_fk() -> None:
    patient_fqn = "db.schema.patient"
    hospital_fqn = "db.schema.hospital"
    lab_fqn = "db.schema.laboratory"

    patient_table = CatalogTable(
        table_fqn=patient_fqn,
        service_name="db",
        database_name="db",
        schema_name="schema",
        table_name="patient",
        sql_identifier="patient",
        columns=[
            _col(patient_fqn, "patient_id", "integer", is_pk=True, pos=1),
            _col(patient_fqn, "name", "text", pos=2),
        ],
        primary_key_column_names=["patient_id"],
    )
    hospital_table = CatalogTable(
        table_fqn=hospital_fqn,
        service_name="db",
        database_name="db",
        schema_name="schema",
        table_name="hospital",
        sql_identifier="hospital",
        columns=[
            _col(hospital_fqn, "region_code", "text", is_pk=True, pos=1),
            _col(hospital_fqn, "hospital_id", "integer", is_pk=True, pos=2),
            _col(hospital_fqn, "hospital_name", "text", pos=3),
        ],
        primary_key_column_names=["region_code", "hospital_id"],
    )
    lab_table = CatalogTable(
        table_fqn=lab_fqn,
        service_name="db",
        database_name="db",
        schema_name="schema",
        table_name="laboratory",
        sql_identifier="laboratory",
        columns=[
            _col(lab_fqn, "lab_id", "integer", is_pk=True, pos=1),
            _col(lab_fqn, "patient_id", "integer", pos=2),
            _col(lab_fqn, "region_code", "text", pos=3),
            _col(lab_fqn, "hospital_id", "integer", pos=4),
            _col(lab_fqn, "test_result", "text", pos=5),
        ],
        primary_key_column_names=["lab_id"],
        foreign_keys=[
            CatalogForeignKey(
                from_table_fqn=lab_fqn,
                from_column_names=["patient_id"],
                to_table_fqn=patient_fqn,
                to_column_names=["patient_id"],
                relationship_name="lab_patient_fk",
            ),
            CatalogForeignKey(
                from_table_fqn=lab_fqn,
                from_column_names=["region_code", "hospital_id"],
                to_table_fqn=hospital_fqn,
                to_column_names=["region_code", "hospital_id"],
                relationship_name="lab_hospital_composite_fk",
            ),
        ],
    )

    catalog = InMemoryCatalog()
    catalog.upsert_tables([patient_table, hospital_table, lab_table])

    expander = RelationshipExpander(catalog)
    seed = [
        RankedTableCandidate(
            table_fqn=patient_table.table_fqn,
            ranking_score=10.0,
            candidates=(),
            matched_fields=("table_name",),
            matched_column_names=("name",),
        )
    ]
    allowed_fqns = {patient_table.table_fqn, lab_table.table_fqn, hospital_table.table_fqn}

    # Conditional mode: fails because 'laboratory' is not in question
    res_cond = expander.expand_one_hop_relationships(
        question="What is the test result of patients?",
        ranked_table_candidates=seed,
        allowed_table_fqns=allowed_fqns,
        max_hydrated_tables=8,
        max_relationships=16,
        expansion_mode="conditional",
    )
    assert patient_table.table_fqn in res_cond.table_fqns
    assert lab_table.table_fqn not in res_cond.table_fqns

    # Unconditional mode (A2): successfully expands incoming FK neighbor
    res_uncond = expander.expand_one_hop_relationships(
        question="What is the test result of patients?",
        ranked_table_candidates=seed,
        allowed_table_fqns=allowed_fqns,
        max_hydrated_tables=8,
        max_relationships=16,
        expansion_mode="unconditional",
    )
    assert patient_table.table_fqn in res_uncond.table_fqns
    assert lab_table.table_fqn in res_uncond.table_fqns
    assert len(res_uncond.relationships) == 1
    assert res_uncond.relationships[0].from_table_fqn == lab_table.table_fqn


def test_relationship_expander_table_budget_and_acl_isolation() -> None:
    t_a = "db.schema.a"
    t_b = "db.schema.b"
    t_sec = "db.schema.secret"

    table_a = CatalogTable(
        table_fqn=t_a,
        service_name="db",
        database_name="db",
        schema_name="schema",
        table_name="a",
        sql_identifier="a",
        columns=[_col(t_a, "id", is_pk=True)],
    )
    table_b = CatalogTable(
        table_fqn=t_b,
        service_name="db",
        database_name="db",
        schema_name="schema",
        table_name="b",
        sql_identifier="b",
        columns=[_col(t_b, "id", is_pk=True), _col(t_b, "a_id")],
        foreign_keys=[
            CatalogForeignKey(
                from_table_fqn=t_b,
                from_column_names=["a_id"],
                to_table_fqn=t_a,
                to_column_names=["id"],
            )
        ],
    )
    table_secret = CatalogTable(
        table_fqn=t_sec,
        service_name="db",
        database_name="db",
        schema_name="schema",
        table_name="secret",
        sql_identifier="secret",
        columns=[_col(t_sec, "id", is_pk=True), _col(t_sec, "a_id")],
        foreign_keys=[
            CatalogForeignKey(
                from_table_fqn=t_sec,
                from_column_names=["a_id"],
                to_table_fqn=t_a,
                to_column_names=["id"],
            )
        ],
    )
    catalog = InMemoryCatalog()
    catalog.upsert_tables([table_a, table_b, table_secret])

    expander = RelationshipExpander(catalog)
    seed = [
        RankedTableCandidate(
            table_fqn=table_a.table_fqn,
            ranking_score=10.0,
            candidates=(),
            matched_fields=("table_name",),
            matched_column_names=("id",),
        )
    ]
    allowed_fqns = {table_a.table_fqn, table_b.table_fqn}

    res = expander.expand_one_hop_relationships(
        question="find all items",
        ranked_table_candidates=seed,
        allowed_table_fqns=allowed_fqns,
        max_hydrated_tables=8,
        max_relationships=16,
        expansion_mode="unconditional",
    )
    assert table_a.table_fqn in res.table_fqns
    assert table_b.table_fqn in res.table_fqns
    assert table_secret.table_fqn not in res.table_fqns
    for r in res.relationships:
        assert r.from_table_fqn in allowed_fqns
        assert r.to_table_fqn in allowed_fqns

    res_budget = expander.expand_one_hop_relationships(
        question="find all items",
        ranked_table_candidates=seed,
        allowed_table_fqns=allowed_fqns,
        max_hydrated_tables=1,
        max_relationships=16,
        expansion_mode="unconditional",
    )
    assert res_budget.table_fqns == (table_a.table_fqn,)


def test_column_fill_to_budget_retains_name_like_and_filter_columns() -> None:
    t_hero = "db.schema.superhero"
    hero_table = CatalogTable(
        table_fqn=t_hero,
        service_name="db",
        database_name="db",
        schema_name="schema",
        table_name="superhero",
        sql_identifier="superhero",
        description="superhero characters fact table",
        columns=[
            _col(t_hero, "id", is_pk=True, pos=1),
            _col(t_hero, "superhero_name", pos=2),
            _col(t_hero, "full_name", pos=3),
            _col(t_hero, "gender", pos=4),
            _col(t_hero, "eye_color", pos=5),
            _col(t_hero, "hair_color", pos=6),
            _col(t_hero, "skin_color", pos=7),
            _col(t_hero, "height_cm", "numeric", pos=8),
            _col(t_hero, "alignment", pos=9),
            _col(t_hero, "weight_kg", "numeric", pos=10),
        ],
        primary_key_column_names=["id"],
    )

    catalog = InMemoryCatalog()
    catalog.upsert_tables([hero_table])
    doc_builder = CatalogSearchDocumentBuilder()
    # Index only the table document so columns are not pre-matched by retrieval
    docs = [
        doc
        for doc in doc_builder.build_search_documents(hero_table)
        if doc.document_type == "table"
    ]
    retriever = SchemaRetriever(InMemorySchemaSearch(docs))
    auth_srv = AuthorizationService(SimpleAccessPolicy([hero_table]))

    user = UserIdentity(user_id="analyst", roles=["analyst"])

    question = "superhero profiles and details"

    # Baseline builder (fill_column_budget=False): only PK and minimum 3 columns are kept
    budget_base = GroundingBudget(max_columns_per_table=12, fill_column_budget=False)
    builder_base = GroundingContextBuilder(
        catalog=catalog,
        schema_retriever=retriever,
        authorization_service=auth_srv,
        grounding_budget=budget_base,
    )
    ctx_base = builder_base.build_grounding_context(
        QueryRequest(question=question),
        user_identity=user,
    )
    base_cols = [c.name for c in ctx_base.tables[0].columns]
    assert len(base_cols) == 3

    # Remediation builder (fill_column_budget=True): fills all 10 columns up to budget
    budget_fix = GroundingBudget(max_columns_per_table=12, fill_column_budget=True)
    builder_fix = GroundingContextBuilder(
        catalog=catalog,
        schema_retriever=retriever,
        authorization_service=auth_srv,
        grounding_budget=budget_fix,
    )
    ctx_fix = builder_fix.build_grounding_context(
        QueryRequest(question=question),
        user_identity=user,
    )
    fix_cols = [c.name for c in ctx_fix.tables[0].columns]

    assert len(fix_cols) == 10
    assert "superhero_name" in fix_cols
    assert "height_cm" in fix_cols
    assert "alignment" in fix_cols
    assert fix_cols == [c.column_name for c in hero_table.columns]


def test_small_db_fallback_includes_all_authorized_tables_and_preserves_acl() -> None:
    t1_fqn = "db.schema.t1"
    t2_fqn = "db.schema.t2"
    t3_fqn = "db.schema.t3"

    table_1 = CatalogTable(
        table_fqn=t1_fqn,
        service_name="db",
        database_name="db",
        schema_name="schema",
        table_name="t1",
        sql_identifier="t1",
        columns=[_col(t1_fqn, "id", is_pk=True, pos=1), _col(t1_fqn, "c1", pos=2)],
        primary_key_column_names=["id"],
    )
    table_2 = CatalogTable(
        table_fqn=t2_fqn,
        service_name="db",
        database_name="db",
        schema_name="schema",
        table_name="t2",
        sql_identifier="t2",
        columns=[_col(t2_fqn, "id", is_pk=True, pos=1), _col(t2_fqn, "t1_id", pos=2)],
        primary_key_column_names=["id"],
        foreign_keys=[
            CatalogForeignKey(
                from_table_fqn=t2_fqn,
                from_column_names=["t1_id"],
                to_table_fqn=t1_fqn,
                to_column_names=["id"],
            )
        ],
    )
    table_3 = CatalogTable(
        table_fqn=t3_fqn,
        service_name="db",
        database_name="db",
        schema_name="schema",
        table_name="t3",
        sql_identifier="t3",
        columns=[_col(t3_fqn, "id", is_pk=True, pos=1), _col(t3_fqn, "secret_val", pos=2)],
        primary_key_column_names=["id"],
    )

    catalog = InMemoryCatalog()
    catalog.upsert_tables([table_1, table_2, table_3])

    auth_srv = AuthorizationService(SimpleAccessPolicy([table_1, table_2]))
    doc_builder = CatalogSearchDocumentBuilder()
    docs = [doc for t in [table_1, table_2] for doc in doc_builder.build_search_documents(t)]
    retriever = SchemaRetriever(InMemorySchemaSearch(docs))
    user = UserIdentity(user_id="user1")

    budget = GroundingBudget(small_db_threshold=3, fill_column_budget=True)
    builder = GroundingContextBuilder(
        catalog=catalog,
        schema_retriever=retriever,
        authorization_service=auth_srv,
        grounding_budget=budget,
    )
    ctx = builder.build_grounding_context(
        QueryRequest(question="random unrelated query"),
        user_identity=user,
    )

    hydrated_tables = {t.sql_identifier for t in ctx.tables}
    assert hydrated_tables == {"t1", "t2"}
    assert "t3" not in hydrated_tables
    assert len(ctx.tables[0].columns) >= 2
    assert len(ctx.tables[1].columns) >= 2
