import asyncio
import logging
from typing import Final

from fastapi.responses import JSONResponse, Response

from openai_batch_proxy.batch.handler import BatchHandler, DisconnectedError
from openai_batch_proxy.batch.hasher import hash_request
from openai_batch_proxy.batch.redis_store import RedisStore
from openai_batch_proxy.routes_dispatch import ModeRequest

logger: Final = logging.getLogger(__name__)


class BatchProxyHandler:
    """Handler that routes requests through the OpenAI Batch API."""

    def __init__(self, batch_handler: BatchHandler, redis_store: RedisStore) -> None:
        self._batch_handler = batch_handler
        self._redis_store = redis_store

    async def handle(self, mr: ModeRequest) -> Response:
        logger.debug("BatchProxyHandler: received %s model=%s",
                      mr.endpoint_path, mr.body.get("model", "?"))
        disconnect_event = asyncio.Event()

        async def monitor_disconnect() -> None:
            while not await mr.request.is_disconnected():
                await asyncio.sleep(1)
            disconnect_event.set()

        monitor_task = asyncio.create_task(monitor_disconnect())

        try:
            result = await self._batch_handler.handle_request(
                caller_key=mr.caller_key,
                request_body=mr.body,
                endpoint=mr.endpoint_path,
                disconnect_event=disconnect_event,
            )
            # Successful delivery - invalidate retry buffer
            request_hash = hash_request(mr.body)
            await self._redis_store.delete_retry_buffer(mr.caller_key, request_hash)
            return JSONResponse(content=result)
        except DisconnectedError:
            return Response(status_code=499)
        finally:
            monitor_task.cancel()
