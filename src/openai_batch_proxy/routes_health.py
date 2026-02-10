import logging
from typing import Final

from fastapi import APIRouter

from openai_batch_proxy.schemas import HealthResponse

logger: Final = logging.getLogger(__name__)

router: Final = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    """Health check endpoint. No authentication required."""
    logger.debug("Health check requested")
    return HealthResponse(status="healthy")
