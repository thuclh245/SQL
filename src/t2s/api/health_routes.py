from fastapi import APIRouter, Request

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
async def read_liveness() -> dict[str, str]:
    return {"status": "live"}


@router.get("/ready")
async def read_readiness(request: Request) -> dict[str, str]:
    settings = request.app.state.settings
    return {"status": "ready", "environment": settings.environment}
