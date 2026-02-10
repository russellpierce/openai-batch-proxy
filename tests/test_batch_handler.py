import asyncio
import json
from typing import Final
from unittest.mock import AsyncMock, patch

import pytest

from openai_batch_proxy.batch.handler import BatchHandler, DisconnectedError
from openai_batch_proxy.batch.openai_client import BatchFailedError
from openai_batch_proxy.errors import BatchProxyError
from openai_batch_proxy.key_config import ApiKeyEntry

TEST_CALLER_KEY: Final = "sk-test-caller"
TEST_OPENAI_KEY: Final = "sk-test-openai"
TEST_ENDPOINT: Final = "/v1/chat/completions"
TEST_REQUEST_BODY: Final = {
    "model": "gpt-4o-mini",
    "messages": [{"role": "user", "content": "Hello"}],
}
TEST_RESPONSE: Final = {
    "id": "chatcmpl-test",
    "object": "chat.completion",
    "created": 1234567890,
    "model": "gpt-4o-mini",
    "choices": [
        {
            "index": 0,
            "message": {"role": "assistant", "content": "Hello!"},
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
}


@pytest.fixture
def key_lookup() -> dict[str, ApiKeyEntry]:
    return {
        TEST_CALLER_KEY: ApiKeyEntry(
            caller_key=TEST_CALLER_KEY,
            openai_key=TEST_OPENAI_KEY,
            retry_buffer_ttl_seconds=3600,
        )
    }


@pytest.fixture
def handler(mock_redis_store: AsyncMock, key_lookup: dict[str, ApiKeyEntry]) -> BatchHandler:
    return BatchHandler(redis_store=mock_redis_store, key_lookup=key_lookup)


@pytest.fixture
def disconnect_event() -> asyncio.Event:
    return asyncio.Event()


@pytest.mark.asyncio
async def test_cache_hit(
    handler: BatchHandler,
    mock_redis_store: AsyncMock,
    disconnect_event: asyncio.Event,
) -> None:
    """Retry buffer hit returns cached response and invalidates."""
    mock_redis_store.get_retry_buffer.return_value = json.dumps(TEST_RESPONSE).encode()

    result = await handler.handle_request(
        caller_key=TEST_CALLER_KEY,
        request_body=dict(TEST_REQUEST_BODY),
        endpoint=TEST_ENDPOINT,
        disconnect_event=disconnect_event,
    )

    assert result["id"] == "chatcmpl-test"
    mock_redis_store.delete_retry_buffer.assert_called_once()


@pytest.mark.asyncio
async def test_batch_submit_poll_complete(
    handler: BatchHandler,
    mock_redis_store: AsyncMock,
    mock_openai_client: AsyncMock,
    disconnect_event: asyncio.Event,
) -> None:
    """Normal batch flow: submit, poll, return result."""
    with patch.object(handler, "_get_openai_client", return_value=mock_openai_client):
        result = await handler.handle_request(
            caller_key=TEST_CALLER_KEY,
            request_body=dict(TEST_REQUEST_BODY),
            endpoint=TEST_ENDPOINT,
            disconnect_event=disconnect_event,
        )

    assert result["id"] == "chatcmpl-test"
    mock_openai_client.submit_batch.assert_called_once()
    mock_openai_client.poll_batch.assert_called_once()
    mock_redis_store.set_retry_buffer.assert_called_once()


@pytest.mark.asyncio
async def test_batch_submit_failure_falls_back_to_sync(
    handler: BatchHandler,
    mock_openai_client: AsyncMock,
    disconnect_event: asyncio.Event,
) -> None:
    """Batch submission failure falls back to sync API."""
    mock_openai_client.submit_batch.side_effect = Exception("Upload failed")

    with patch.object(handler, "_get_openai_client", return_value=mock_openai_client):
        result = await handler.handle_request(
            caller_key=TEST_CALLER_KEY,
            request_body=dict(TEST_REQUEST_BODY),
            endpoint=TEST_ENDPOINT,
            disconnect_event=disconnect_event,
        )

    assert result["id"] == "chatcmpl-sync"
    mock_openai_client.sync_call.assert_called_once()


@pytest.mark.asyncio
async def test_batch_failure_falls_back_to_sync(
    handler: BatchHandler,
    mock_openai_client: AsyncMock,
    disconnect_event: asyncio.Event,
) -> None:
    """Batch poll failure falls back to sync API."""
    mock_openai_client.poll_batch.side_effect = BatchFailedError("Batch failed")

    with patch.object(handler, "_get_openai_client", return_value=mock_openai_client):
        result = await handler.handle_request(
            caller_key=TEST_CALLER_KEY,
            request_body=dict(TEST_REQUEST_BODY),
            endpoint=TEST_ENDPOINT,
            disconnect_event=disconnect_event,
        )

    assert result["id"] == "chatcmpl-sync"
    mock_openai_client.sync_call.assert_called_once()


@pytest.mark.asyncio
async def test_unsupported_model_raises_error(
    handler: BatchHandler,
    mock_openai_client: AsyncMock,
    disconnect_event: asyncio.Event,
) -> None:
    """Unsupported model returns meaningful error."""
    mock_openai_client.check_model_supports_batch.return_value = False

    with (
        patch.object(handler, "_get_openai_client", return_value=mock_openai_client),
        pytest.raises(BatchProxyError, match="does not support the Batch API"),
    ):
        await handler.handle_request(
            caller_key=TEST_CALLER_KEY,
            request_body={"model": "gpt-realtime-mini", "messages": []},
            endpoint=TEST_ENDPOINT,
            disconnect_event=disconnect_event,
        )


@pytest.mark.asyncio
async def test_disconnect_during_poll(
    handler: BatchHandler,
    mock_openai_client: AsyncMock,
) -> None:
    """Disconnect during poll triggers batch cancellation."""
    disconnect_event = asyncio.Event()

    # Make poll_batch hang, then trigger disconnect
    async def slow_poll(_batch_id: str) -> dict[str, object]:
        await asyncio.sleep(10)
        return TEST_RESPONSE

    mock_openai_client.poll_batch.side_effect = slow_poll

    async def trigger_disconnect() -> None:
        await asyncio.sleep(0.1)
        disconnect_event.set()

    with patch.object(handler, "_get_openai_client", return_value=mock_openai_client):
        asyncio.create_task(trigger_disconnect())
        with pytest.raises(DisconnectedError):
            await handler.handle_request(
                caller_key=TEST_CALLER_KEY,
                request_body=dict(TEST_REQUEST_BODY),
                endpoint=TEST_ENDPOINT,
                disconnect_event=disconnect_event,
            )

    mock_openai_client.cancel_batch.assert_called_once()
