import structlog
from fastapi import Request
from fastapi.responses import JSONResponse

from t2s.contracts import ErrorDetail, ErrorResponse
from t2s.errors import T2SError

logger = structlog.get_logger(__name__)


async def handle_t2s_error(request: Request, exc: Exception) -> JSONResponse:
    error_code = exc.error_code if isinstance(exc, T2SError) else "application_error"
    logger.warning(
        "application_error_response",
        error_code=error_code,
        exc_info=exc,
    )
    return JSONResponse(
        status_code=500,
        content=_build_error_response(
            request=request,
            error_code=error_code.upper(),
            message="The request could not be processed.",
        ).model_dump(),
    )


async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unexpected_error_response")
    return JSONResponse(
        status_code=500,
        content=_build_error_response(
            request=request,
            error_code="INTERNAL_ERROR",
            message="An internal error occurred.",
        ).model_dump(),
    )


def _build_error_response(request: Request, error_code: str, message: str) -> ErrorResponse:
    return ErrorResponse(
        error=ErrorDetail(code=error_code, message=message),
        request_id=getattr(request.state, "request_id", None),
        trace_id=getattr(request.state, "trace_id", None),
        run_id=getattr(request.state, "run_id", None),
    )
