"""Tests for batch_proxy mode handler via dispatch router."""

from typing import Final
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from openai_batch_proxy.auth import create_auth_dependency
from openai_batch_proxy.errors import register_error_handlers
from openai_batch_proxy.key_config import ApiKeyEntry
from openai_batch_proxy.modes.batch_proxy.handler import BatchProxyHandler
from openai_batch_proxy.override_proxy.config import RouteConfig
from openai_batch_proxy.routes_dispatch import ModeHandler, create_dispatch_router

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
def key_lookup() -> dict[str, ApiKeyEntry]:
    """Create test key lookup."""
    return {
        TEST_CALLER_KEY: ApiKeyEntry(
            caller_key=TEST_CALLER_KEY,
            openai_key=TEST_OPENAI_KEY,
        )
    }


@pytest.fixture
def batch_app(key_lookup: dict[str, ApiKeyEntry]) -> FastAPI:
    """Create a FastAPI app with batch_proxy mode via dispatch router."""
    app = FastAPI()
    register_error_handlers(app)

    auth_dep = create_auth_dependency(frozenset(key_lookup.keys()))

    # Create mock batch handler
    mock_batch_handler = AsyncMock()
    mock_batch_handler.handle_request = AsyncMock(return_value=dict(TEST_RESPONSE))

    mock_redis_store = AsyncMock()
    mock_redis_store.delete_retry_buffer = AsyncMock()

    # Create the batch proxy handler with mocks
    batch_proxy_handler = BatchProxyHandler(mock_batch_handler, mock_redis_store)

    # Mock passthrough handler for other paths
    mock_passthrough = AsyncMock()
    mock_passthrough.handle = AsyncMock()

    routes = {
        "/v1/chat/completions": RouteConfig(mode="batch_proxy"),
    }
    mode_handlers: dict[str, ModeHandler] = {
        "batch_proxy": batch_proxy_handler,
        "passthrough": mock_passthrough,
    }

    app.include_router(create_dispatch_router(routes, mode_handlers, key_lookup, auth_dep))
    app.state.mock_batch_handler = mock_batch_handler
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
