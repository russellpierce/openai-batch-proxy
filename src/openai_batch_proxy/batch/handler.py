import asyncio
import contextlib
import json
import logging
import uuid
from typing import Final

from openai_batch_proxy.batch.hasher import hash_request
from openai_batch_proxy.batch.openai_client import BatchFailedError, OpenAIBatchClient
from openai_batch_proxy.batch.redis_store import RedisStore
from openai_batch_proxy.errors import BatchProxyError
from openai_batch_proxy.key_config import ApiKeyEntry

logger: Final = logging.getLogger(__name__)


class DisconnectedError(Exception):
    """Raised when the caller disconnects during batch processing."""


class BatchHandler:
    """Orchestrates the full batch proxy lifecycle for a single request."""

    def __init__(
        self,
        redis_store: RedisStore,
        key_lookup: dict[str, ApiKeyEntry],
    ) -> None:
        self._redis = redis_store
        self._key_lookup = key_lookup
        self._openai_clients: dict[str, OpenAIBatchClient] = {}

    def _get_openai_client(self, openai_key: str) -> OpenAIBatchClient:
        """Get or create an OpenAI client for a given key."""
        if openai_key not in self._openai_clients:
            self._openai_clients[openai_key] = OpenAIBatchClient(api_key=openai_key)
        return self._openai_clients[openai_key]

    async def handle_request(
        self,
        caller_key: str,
        request_body: dict[str, object],
        endpoint: str,
        disconnect_event: asyncio.Event,
    ) -> dict[str, object]:
        """
        Full batch proxy lifecycle.

        Args:
            caller_key: The authenticated caller's API key
            request_body: The raw request body dict
            endpoint: e.g., "/v1/chat/completions"
            disconnect_event: Set when the caller disconnects

        Returns:
            OpenAI-format response dict
        """
        key_entry = self._key_lookup[caller_key]
        client = self._get_openai_client(key_entry.openai_key)
        request_hash = hash_request(request_body)

        # 1. Check retry buffer
        cached = await self._redis.get_retry_buffer(caller_key, request_hash)
        if cached:
            logger.info(f"Retry buffer hit for hash={request_hash[:12]}...")
            response: dict[str, object] = json.loads(cached)
            await self._redis.delete_retry_buffer(caller_key, request_hash)
            return response
        logger.debug("Step 1/4 retry-buffer: miss  hash=%s", request_hash[:12])

        # 2. Validate model supports batch
        model = str(request_body.get("model", ""))
        if not await client.check_model_supports_batch(model):
            raise BatchProxyError(
                f"Model '{model}' does not support the Batch API. "
                "Use a supported model or switch to workflow mode."
            )
        logger.debug("Step 2/4 model-check: %s OK", model)

        # 3. Submit batch
        request_id = uuid.uuid4().hex
        try:
            batch_id = await client.submit_batch(endpoint, request_body, request_id)
        except Exception:
            logger.warning("Batch submission failed, falling back to sync", exc_info=True)
            return await client.sync_call(request_body)
        logger.info("Step 3/4 batch-submitted: batch_id=%s  endpoint=%s  model=%s",
                     batch_id, endpoint, model)

        await self._redis.store_batch_id(request_id, batch_id)

        # 4. Poll with disconnect detection
        logger.debug("Step 4/4 polling batch_id=%s ...", batch_id)
        try:
            poll_task = asyncio.create_task(client.poll_batch(batch_id))
            disconnect_task = asyncio.create_task(disconnect_event.wait())

            done, pending = await asyncio.wait(
                {poll_task, disconnect_task},
                return_when=asyncio.FIRST_COMPLETED,
            )

            for task in pending:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task

            if disconnect_task in done:
                logger.info(f"Caller disconnected, cancelling batch {batch_id}")
                final_status = await client.cancel_batch(batch_id)
                if final_status == "completed":
                    # Batch finished before cancel took effect - try to cache
                    try:
                        result = await client.poll_batch(batch_id)
                        await self._redis.set_retry_buffer(
                            caller_key,
                            request_hash,
                            json.dumps(result).encode(),
                            key_entry.retry_buffer_ttl_seconds,
                        )
                    except Exception:
                        logger.warning("Failed to cache completed batch on disconnect")
                raise DisconnectedError("Caller disconnected")

            result = poll_task.result()

        except BatchFailedError:
            logger.warning(f"Batch {batch_id} failed, falling back to sync", exc_info=True)
            result = await client.sync_call(request_body)

        # 5. Cache result in retry buffer
        await self._redis.set_retry_buffer(
            caller_key,
            request_hash,
            json.dumps(result).encode(),
            key_entry.retry_buffer_ttl_seconds,
        )

        return result
