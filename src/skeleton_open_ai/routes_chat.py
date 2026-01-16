import logging
import time
import uuid
from collections.abc import Callable
from typing import Final

from fastapi import APIRouter, Depends

from skeleton_open_ai.errors import InvalidRequestError
from skeleton_open_ai.schemas import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
    Choice,
    Usage,
)
from skeleton_open_ai.workflow import run_workflow

logger: Final = logging.getLogger(__name__)


def create_chat_router(
    available_models: list[str],
    auth_dependency: Callable[..., str],
) -> APIRouter:
    """Create router for chat completion endpoint with injected dependencies."""

    router = APIRouter(tags=["chat"])

    @router.post("/v1/chat/completions", response_model=ChatCompletionResponse)
    def create_chat_completion(
        request: ChatCompletionRequest,
        _api_key: str = Depends(auth_dependency),
    ) -> ChatCompletionResponse:
        """
        Create a chat completion. Requires authentication.

        The model must be in the configured list of available models.
        """
        logger.info(f"Chat completion requested for model: {request.model}")
        logger.debug(f"Request: {request.model_dump_json()}")

        # Validate model
        if request.model not in available_models:
            raise InvalidRequestError(
                message=f"Model '{request.model}' not found. Available models: {available_models}",
                error_code="model_not_found",
            )

        # Extract messages and call workflow
        # NO try/except - let workflow errors crash the request
        response_text = run_workflow(messages=request.messages, model=request.model)

        # Build response
        completion_id = f"chatcmpl-{uuid.uuid4().hex}"
        created_timestamp = int(time.time())

        response = ChatCompletionResponse(
            id=completion_id,
            created=created_timestamp,
            model=request.model,
            choices=[
                Choice(
                    index=0,
                    message=ChatMessage(role="assistant", content=response_text),
                    finish_reason="stop",
                )
            ],
            usage=Usage(prompt_tokens=0, completion_tokens=0, total_tokens=0),
        )

        logger.debug(f"Response: {response.model_dump_json()}")
        return response

    return router
