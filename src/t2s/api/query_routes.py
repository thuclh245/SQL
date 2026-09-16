from uuid import uuid4

import structlog
from fastapi import APIRouter, Request

from t2s.contracts import QueryDecision, QueryRequest, QueryResponse
from t2s.observability import bind_query_run_correlation
from t2s.runtime import TextToSqlRuntime
from t2s.security import UserIdentity

router = APIRouter(prefix="/v1", tags=["query"])
logger = structlog.get_logger(__name__)


@router.post("/query", response_model=QueryResponse)
async def create_query_run(query_request: QueryRequest, request: Request) -> QueryResponse:
    run_id = str(uuid4())
    bind_query_run_correlation(run_id=run_id, request=request)
    request_id = request.state.request_id
    trace_id = request.state.trace_id

    logger.info(
        "query_run_created",
        client_request_id=query_request.client_request_id,
    )

    runtime: TextToSqlRuntime | None = getattr(request.app.state, "runtime", None)
    if runtime is not None:
        user_identity = _build_user_identity(request)
        result = await runtime.execute_query_pipeline(
            query_request=query_request,
            user_identity=user_identity,
            run_id=run_id,
        )
        return result.to_query_response(request_id=request_id, trace_id=trace_id)

    return QueryResponse(
        request_id=request_id,
        run_id=run_id,
        trace_id=trace_id,
        status="abstain",
        answer=None,
        sql=None,
        explanation=(
            "T2S API is running, but no TextToSqlRuntime is configured for this deployment."
        ),
        decision=QueryDecision(
            score=None,
            policy="runtime-not-configured-v1",
            reason=(
                "Configure runtime_sqlite_database_path, runtime_catalog_tables_path, "
                "and vllm_base_url to enable the T2S runtime pipeline."
            ),
        ),
        evidence_summary=[],
        warnings=["Runtime pipeline was not invoked because application runtime is unset."],
    )


def _build_user_identity(request: Request) -> UserIdentity:
    roles_header = request.headers.get("x-user-roles", "")
    roles = frozenset(role.strip() for role in roles_header.split(",") if role.strip())
    return UserIdentity(
        user_id=request.headers.get("x-user-id") or request.app.state.settings.runtime_api_user_id,
        tenant_id=request.headers.get("x-tenant-id"),
        roles=roles,
    )
