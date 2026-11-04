"""Health Check API Route."""

from datetime import datetime, timezone
from fastapi import APIRouter
from app.interfaces.api.schemas.api_schemas import HealthResponse

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(
        status="ok",
        version="0.1.0",
        database="connected",
        timestamp=datetime.now(timezone.utc),
    )

