import asyncio
import logging
from typing import Final

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from openai_batch_proxy.schemas import HealthResponse

logger: Final = logging.getLogger(__name__)

router: Final = APIRouter(tags=["health"])

REDIS_PING_TIMEOUT_SECONDS: Final = 2.0


@router.get("/health", response_model=HealthResponse)
async def health_check(request: Request) -> HealthResponse | JSONResponse:
    """Health check endpoint. No authentication required."""
    logger.debug("Health check requested")

    redis_client = getattr(request.app.state, "external_redis_client", None)

    if redis_client is not None:
        try:
            await asyncio.wait_for(
                redis_client.ping(),
                timeout=REDIS_PING_TIMEOUT_SECONDS,
            )
        except Exception:
            logger.warning("Health check failed: Redis unreachable")
            return JSONResponse(
                status_code=503,
                content=HealthResponse(
                    status="unhealthy", reason="redis unreachable"
                ).model_dump(),
            )

    return HealthResponse(status="healthy")
