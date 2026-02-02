import asyncio
import logging
from collections.abc import Callable
from typing import Final

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response

from skeleton_open_ai.batch.handler import BatchHandler, DisconnectedError
from skeleton_open_ai.batch.hasher import hash_request
from skeleton_open_ai.batch.redis_store import RedisStore
from skeleton_open_ai.schemas import ChatCompletionRequest

logger: Final = logging.getLogger(__name__)


def create_batch_chat_router(
    batch_handler: BatchHandler,
    redis_store: RedisStore,
    auth_dependency: Callable[..., str],
) -> APIRouter:
    """Create router for batch proxy chat completion endpoint."""

    router = APIRouter(tags=["batch-chat"])

    @router.post("/v1/chat/completions")
    async def create_batch_chat_completion(
        request: Request,
        body: ChatCompletionRequest,
        api_key: str = Depends(auth_dependency),
    ) -> Response:
        """Batch proxy chat completion endpoint."""
        disconnect_event = asyncio.Event()

        async def monitor_disconnect() -> None:
            while not await request.is_disconnected():
                await asyncio.sleep(1)
            disconnect_event.set()

        monitor_task = asyncio.create_task(monitor_disconnect())

        try:
            result = await batch_handler.handle_request(
                caller_key=api_key,
                request_body=body.model_dump(exclude_none=True),
                endpoint="/v1/chat/completions",
                disconnect_event=disconnect_event,
            )
            # Successful delivery - invalidate retry buffer
            request_hash = hash_request(body.model_dump(exclude_none=True))
            await redis_store.delete_retry_buffer(api_key, request_hash)
            return JSONResponse(content=result)
        except DisconnectedError:
            return Response(status_code=499)
        finally:
            monitor_task.cancel()

    return router
