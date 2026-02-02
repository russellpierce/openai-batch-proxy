from typing import Final
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from skeleton_open_ai.auth import create_auth_dependency
from skeleton_open_ai.batch.handler import BatchHandler
from skeleton_open_ai.batch.redis_store import RedisStore
from skeleton_open_ai.batch.routes_chat import create_batch_chat_router
from skeleton_open_ai.errors import register_error_handlers
from skeleton_open_ai.key_config import ApiKeyEntry

TEST_CALLER_KEY: Final = "sk-test-caller"
TEST_OPENAI_KEY: Final = "sk-openai-test"
TEST_RESPONSE: Final = {
    "id": "chatcmpl-batch",
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
def batch_app() -> FastAPI:
    """Create a FastAPI app with batch chat router."""
    app = FastAPI()
    register_error_handlers(app)

    key_lookup = {
        TEST_CALLER_KEY: ApiKeyEntry(
            caller_key=TEST_CALLER_KEY,
            openai_key=TEST_OPENAI_KEY,
        )
    }
    auth_dep = create_auth_dependency(frozenset(key_lookup.keys()))

    mock_redis = AsyncMock(spec=RedisStore)
    mock_redis.delete_retry_buffer = AsyncMock()

    mock_handler = AsyncMock(spec=BatchHandler)
    mock_handler.handle_request = AsyncMock(return_value=dict(TEST_RESPONSE))

    app.include_router(create_batch_chat_router(mock_handler, mock_redis, auth_dep))
    app.state.mock_handler = mock_handler
    return app


@pytest.fixture
def batch_client(batch_app: FastAPI) -> TestClient:
    return TestClient(batch_app)


def test_valid_request(batch_client: TestClient) -> None:
    """Valid request returns 200 with response."""
    resp = batch_client.post(
        "/v1/chat/completions",
        json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "Hi"}]},
        headers={"Authorization": f"Bearer {TEST_CALLER_KEY}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "chatcmpl-batch"
    assert data["choices"][0]["message"]["content"] == "Hello!"


def test_missing_auth(batch_client: TestClient) -> None:
    """Missing auth returns 401."""
    resp = batch_client.post(
        "/v1/chat/completions",
        json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "Hi"}]},
    )
    assert resp.status_code == 401


def test_invalid_auth(batch_client: TestClient) -> None:
    """Invalid auth returns 401."""
    resp = batch_client.post(
        "/v1/chat/completions",
        json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "Hi"}]},
        headers={"Authorization": "Bearer sk-wrong-key"},
    )
    assert resp.status_code == 401


def test_empty_messages_rejected(batch_client: TestClient) -> None:
    """Empty messages list returns 400."""
    resp = batch_client.post(
        "/v1/chat/completions",
        json={"model": "gpt-4o-mini", "messages": []},
        headers={"Authorization": f"Bearer {TEST_CALLER_KEY}"},
    )
    assert resp.status_code == 400


def test_extra_fields_accepted(batch_client: TestClient) -> None:
    """Extra fields (structured output params) are accepted."""
    resp = batch_client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "Hi"}],
            "response_format": {"type": "json_object"},
        },
        headers={"Authorization": f"Bearer {TEST_CALLER_KEY}"},
    )
    assert resp.status_code == 200
