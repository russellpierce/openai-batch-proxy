import logging
import time
from collections.abc import Callable
from typing import Final

from fastapi import APIRouter, Depends

from skeleton_open_ai.schemas import ModelInfo, ModelsListResponse

logger: Final = logging.getLogger(__name__)


def create_models_router(
    available_models: list[str],
    auth_dependency: Callable[..., str],
) -> APIRouter:
    """Create router for models endpoint with injected dependencies."""

    router = APIRouter(tags=["models"])

    @router.get("/v1/models", response_model=ModelsListResponse)
    def list_models(_api_key: str = Depends(auth_dependency)) -> ModelsListResponse:
        """List available models. Requires authentication."""
        logger.info("Models list requested")

        created_timestamp = int(time.time())
        models = [
            ModelInfo(id=model_id, created=created_timestamp) for model_id in available_models
        ]

        return ModelsListResponse(data=models)

    return router
