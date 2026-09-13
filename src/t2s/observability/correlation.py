from uuid import uuid4

from fastapi import Request, Response
from starlette.middleware.base import RequestResponseEndpoint
from structlog.contextvars import bind_contextvars, clear_contextvars, get_contextvars

REQUEST_ID_HEADER = "x-request-id"
TRACE_ID_HEADER = "x-trace-id"


async def bind_request_correlation(
    request: Request,
    call_next: RequestResponseEndpoint,
) -> Response:
    clear_contextvars()
    request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid4())
    trace_id = request.headers.get(TRACE_ID_HEADER) or str(uuid4())
    request.state.request_id = request_id
    request.state.trace_id = trace_id
    request.state.run_id = None
    bind_contextvars(request_id=request_id, trace_id=trace_id)
    try:
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        response.headers[TRACE_ID_HEADER] = trace_id
        return response
    finally:
        clear_contextvars()


def bind_query_run_correlation(run_id: str, request: Request) -> None:
    request.state.run_id = run_id
    bind_contextvars(run_id=run_id)


def read_correlation_context() -> dict[str, str]:
    contextvars = get_contextvars()
    return {key: str(value) for key, value in contextvars.items()}

