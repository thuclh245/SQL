from uuid import uuid4

import structlog
from fastapi import APIRouter, Request

from t2s.contracts import QueryDecision, QueryRequest, QueryResponse

router = APIRouter(prefix="/v1", tags=["query"])
logger = structlog.get_logger(__name__)


@router.post("/query", response_model=QueryResponse)
async def create_query_run(query_request: QueryRequest, request: Request) -> QueryResponse:
    request_id = str(uuid4())
    run_id = str(uuid4())
    trace_id = str(uuid4())

    logger.info(
        "query_run_created",
        request_id=request_id,
        run_id=run_id,
        trace_id=trace_id,
        client_request_id=query_request.client_request_id,
    )

    return QueryResponse(
        request_id=request_id,
        run_id=run_id,
        trace_id=trace_id,
        status="abstain",
        answer=None,
        sql=None,
        explanation=(
            "T2S foundation is running; SQL generation is intentionally out of scope for P0."
        ),
        decision=QueryDecision(
            score=None,
            policy="foundation-stub-v0",
            reason="No solver, grounding, verifier, or database gateway is wired in P0.",
        ),
        evidence_summary=[],
        warnings=["P0 stub response; no database interaction occurred."],
    )
