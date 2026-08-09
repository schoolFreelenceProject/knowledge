from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_health_service
from app.schemas.health import HealthResponse
from app.services.health_service import HealthService


router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", response_model=HealthResponse)
def liveness() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/ready", response_model=HealthResponse)
def readiness(
    health_service: HealthService = Depends(get_health_service),
) -> HealthResponse:
    response = health_service.check_dependencies()
    if response.status != "ok":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=response.model_dump(mode="json"),
        )

    return response
