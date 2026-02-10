"""Integration tests for the dispatch router across realistic configurations.

Tests verify that mode selection, override application, and passthrough fallback
all work together correctly through the full stack.
"""

import json
from typing import Any, Final
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from openai_batch_proxy.auth import create_auth_dependency
from openai_batch_proxy.errors import register_error_handlers
from openai_batch_proxy.key_config import ApiKeyEntry
from openai_batch_proxy.modes.batch_proxy.handler import BatchProxyHandler
from openai_batch_proxy.modes.passthrough.handler import PassthroughHandler
from openai_batch_proxy.override_proxy.config import (
    OverrideField,
    OverridesConfig,
    RouteConfig,
)
from openai_batch_proxy.routes_dispatch import ModeHandler, create_dispatch_router

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
TEST_CALLER_KEY: Final = "sk-test-caller"
TEST_OPENAI_KEY: Final = "sk-openai-actual"
AUTH_HEADER: Final = {"Authorization": f"Bearer {TEST_CALLER_KEY}"}

BATCH_RESPONSE: Final = {
    "id": "chatcmpl-batch",
    "object": "chat.completion",
    "created": 1234567890,
    "model": "gpt-4o-mini",
    "choices": [
        {
            "index": 0,
            "message": {"role": "assistant", "content": "batch reply"},
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
}

CHAT_BODY: Final = {
    "model": "gpt-4o-mini",
    "messages": [{"role": "user", "content": "Hi"}],
}


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------
@pytest.fixture()
def key_lookup() -> dict[str, ApiKeyEntry]:
    return {
        TEST_CALLER_KEY: ApiKeyEntry(
            caller_key=TEST_CALLER_KEY,
            openai_key=TEST_OPENAI_KEY,
        )
    }


@pytest.fixture()
def auth_dep(key_lookup: dict[str, ApiKeyEntry]) -> Any:
    return create_auth_dependency(frozenset(key_lookup.keys()))


@pytest.fixture()
def mock_batch_handler() -> AsyncMock:
    handler = AsyncMock()
    handler.handle_request = AsyncMock(return_value=dict(BATCH_RESPONSE))
    return handler


@pytest.fixture()
def mock_redis_store() -> AsyncMock:
    store = AsyncMock()
    store.delete_retry_buffer = AsyncMock()
    return store


@pytest.fixture()
def batch_proxy_handler(
    mock_batch_handler: AsyncMock, mock_redis_store: AsyncMock
) -> BatchProxyHandler:
    return BatchProxyHandler(mock_batch_handler, mock_redis_store)


@pytest.fixture()
def passthrough_handler() -> PassthroughHandler:
    return PassthroughHandler()


# ---------------------------------------------------------------------------
# Config factories
# ---------------------------------------------------------------------------
def _build_config_1(
    batch_proxy_handler: ModeHandler,
    passthrough_handler: ModeHandler,
) -> tuple[dict[str, RouteConfig], dict[str, ModeHandler]]:
    """Config 1: /v1/chat/completions -> batch_proxy, no overrides."""
    routes = {
        "/v1/chat/completions": RouteConfig(mode="batch_proxy"),
    }
    mode_handlers: dict[str, ModeHandler] = {
        "batch_proxy": batch_proxy_handler,
        "passthrough": passthrough_handler,
    }
    return routes, mode_handlers


def _build_config_2(
    passthrough_handler: ModeHandler,
) -> tuple[dict[str, RouteConfig], dict[str, ModeHandler]]:
    """Config 2: /v1/chat/completions -> passthrough + overrides."""
    routes = {
        "/v1/chat/completions": RouteConfig(
            mode="passthrough",
            overrides=OverridesConfig(
                body={
                    "service_tier": OverrideField(value="flex", mode="force"),
                    "reasoning.effort": OverrideField(value="low", mode="default"),
                }
            ),
        ),
    }
    mode_handlers: dict[str, ModeHandler] = {
        "passthrough": passthrough_handler,
    }
    return routes, mode_handlers


def _build_config_3(
    batch_proxy_handler: ModeHandler,
    passthrough_handler: ModeHandler,
) -> tuple[dict[str, RouteConfig], dict[str, ModeHandler]]:
    """Config 3: chat -> batch_proxy+override, responses -> passthrough+override."""
    routes = {
        "/v1/chat/completions": RouteConfig(
            mode="batch_proxy",
            overrides=OverridesConfig(
                body={
                    "service_tier": OverrideField(value="flex", mode="force"),
                }
            ),
        ),
        "/v1/responses": RouteConfig(
            mode="passthrough",
            overrides=OverridesConfig(
                body={
                    "reasoning.effort": OverrideField(value="low", mode="default"),
                }
            ),
        ),
    }
    mode_handlers: dict[str, ModeHandler] = {
        "batch_proxy": batch_proxy_handler,
        "passthrough": passthrough_handler,
    }
    return routes, mode_handlers


def _make_app(
    routes: dict[str, RouteConfig],
    mode_handlers: dict[str, ModeHandler],
    key_lookup: dict[str, ApiKeyEntry],
    auth_dep: Any,
) -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(create_dispatch_router(routes, mode_handlers, key_lookup, auth_dep))
    return app


def _mock_httpx_response(
    status_code: int = 200,
    json_body: dict[str, Any] | None = None,
    content: bytes | None = None,
) -> httpx.Response:
    """Build a fake httpx.Response for passthrough mocking."""
    body = content if content is not None else json.dumps(json_body or {}).encode()
    return httpx.Response(
        status_code=status_code,
        content=body,
        headers={"content-type": "application/json"},
    )


# ===================================================================
# Config 1 — batch_proxy, no overrides
# ===================================================================
class TestConfig1:
    """Config 1: /v1/chat/completions -> batch_proxy (no overrides)."""

    def test_chat_delegates_to_batch_proxy(
        self,
        key_lookup: dict[str, ApiKeyEntry],
        auth_dep: Any,
        batch_proxy_handler: BatchProxyHandler,
        passthrough_handler: PassthroughHandler,
        mock_batch_handler: AsyncMock,
    ) -> None:
        routes, handlers = _build_config_1(batch_proxy_handler, passthrough_handler)
        app = _make_app(routes, handlers, key_lookup, auth_dep)

        with TestClient(app) as client:
            resp = client.post("/v1/chat/completions", json=dict(CHAT_BODY), headers=AUTH_HEADER)

        assert resp.status_code == 200
        assert resp.json()["id"] == "chatcmpl-batch"

        mock_batch_handler.handle_request.assert_called_once()
        call_kwargs = mock_batch_handler.handle_request.call_args
        assert call_kwargs.kwargs["caller_key"] == TEST_CALLER_KEY
        assert call_kwargs.kwargs["endpoint"] == "/v1/chat/completions"
        assert call_kwargs.kwargs["request_body"]["model"] == "gpt-4o-mini"

    def test_models_passthrough(
        self,
        key_lookup: dict[str, ApiKeyEntry],
        auth_dep: Any,
        batch_proxy_handler: BatchProxyHandler,
        passthrough_handler: PassthroughHandler,
    ) -> None:
        routes, handlers = _build_config_1(batch_proxy_handler, passthrough_handler)
        app = _make_app(routes, handlers, key_lookup, auth_dep)

        upstream_resp = _mock_httpx_response(json_body={"object": "list", "data": []})

        with patch("openai_batch_proxy.modes.passthrough.handler.httpx.AsyncClient") as MockClient:
            mock_client_instance = AsyncMock()
            mock_client_instance.request = AsyncMock(return_value=upstream_resp)
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client_instance

            with TestClient(app) as client:
                resp = client.get("/v1/models", headers=AUTH_HEADER)

        assert resp.status_code == 200
        mock_client_instance.request.assert_called_once()
        call_kwargs = mock_client_instance.request.call_args
        assert call_kwargs.kwargs["url"] == "https://api.openai.com/v1/models"
        assert call_kwargs.kwargs["headers"]["Authorization"] == f"Bearer {TEST_OPENAI_KEY}"


# ===================================================================
# Config 2 — passthrough + overrides
# ===================================================================
class TestConfig2:
    """Config 2: /v1/chat/completions -> passthrough + overrides."""

    def test_chat_passthrough_with_overrides(
        self,
        key_lookup: dict[str, ApiKeyEntry],
        auth_dep: Any,
        passthrough_handler: PassthroughHandler,
    ) -> None:
        routes, handlers = _build_config_2(passthrough_handler)
        app = _make_app(routes, handlers, key_lookup, auth_dep)

        upstream_resp = _mock_httpx_response(json_body=dict(BATCH_RESPONSE))

        with patch("openai_batch_proxy.modes.passthrough.handler.httpx.AsyncClient") as MockClient:
            mock_client_instance = AsyncMock()
            mock_client_instance.request = AsyncMock(return_value=upstream_resp)
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client_instance

            with TestClient(app) as client:
                resp = client.post(
                    "/v1/chat/completions", json=dict(CHAT_BODY), headers=AUTH_HEADER
                )

        assert resp.status_code == 200

        # Verify overrides were applied to the upstream request
        call_kwargs = mock_client_instance.request.call_args
        sent_body = json.loads(call_kwargs.kwargs["content"])
        # force override: service_tier set to "flex"
        assert sent_body["service_tier"] == "flex"
        # default override: reasoning.effort set since not in original body
        assert sent_body["reasoning"]["effort"] == "low"
        # original fields preserved
        assert sent_body["model"] == "gpt-4o-mini"
        assert sent_body["messages"] == CHAT_BODY["messages"]

    def test_default_override_does_not_clobber_existing(
        self,
        key_lookup: dict[str, ApiKeyEntry],
        auth_dep: Any,
        passthrough_handler: PassthroughHandler,
    ) -> None:
        routes, handlers = _build_config_2(passthrough_handler)
        app = _make_app(routes, handlers, key_lookup, auth_dep)

        upstream_resp = _mock_httpx_response(json_body=dict(BATCH_RESPONSE))
        body_with_reasoning = {
            **CHAT_BODY,
            "reasoning": {"effort": "high"},
        }

        with patch("openai_batch_proxy.modes.passthrough.handler.httpx.AsyncClient") as MockClient:
            mock_client_instance = AsyncMock()
            mock_client_instance.request = AsyncMock(return_value=upstream_resp)
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client_instance

            with TestClient(app) as client:
                resp = client.post(
                    "/v1/chat/completions", json=body_with_reasoning, headers=AUTH_HEADER
                )

        assert resp.status_code == 200
        sent_body = json.loads(mock_client_instance.request.call_args.kwargs["content"])
        # default override should NOT clobber existing reasoning.effort
        assert sent_body["reasoning"]["effort"] == "high"
        # force override still applies
        assert sent_body["service_tier"] == "flex"

    def test_models_passthrough(
        self,
        key_lookup: dict[str, ApiKeyEntry],
        auth_dep: Any,
        passthrough_handler: PassthroughHandler,
    ) -> None:
        routes, handlers = _build_config_2(passthrough_handler)
        app = _make_app(routes, handlers, key_lookup, auth_dep)

        upstream_resp = _mock_httpx_response(json_body={"object": "list", "data": []})

        with patch("openai_batch_proxy.modes.passthrough.handler.httpx.AsyncClient") as MockClient:
            mock_client_instance = AsyncMock()
            mock_client_instance.request = AsyncMock(return_value=upstream_resp)
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client_instance

            with TestClient(app) as client:
                resp = client.get("/v1/models", headers=AUTH_HEADER)

        assert resp.status_code == 200
        call_kwargs = mock_client_instance.request.call_args
        assert call_kwargs.kwargs["url"] == "https://api.openai.com/v1/models"
        assert call_kwargs.kwargs["headers"]["Authorization"] == f"Bearer {TEST_OPENAI_KEY}"


# ===================================================================
# Config 3 — mixed modes with overrides
# ===================================================================
class TestConfig3:
    """Config 3: chat -> batch_proxy+override, responses -> passthrough+override."""

    def test_chat_batch_proxy_with_override(
        self,
        key_lookup: dict[str, ApiKeyEntry],
        auth_dep: Any,
        batch_proxy_handler: BatchProxyHandler,
        passthrough_handler: PassthroughHandler,
        mock_batch_handler: AsyncMock,
    ) -> None:
        routes, handlers = _build_config_3(batch_proxy_handler, passthrough_handler)
        app = _make_app(routes, handlers, key_lookup, auth_dep)

        with TestClient(app) as client:
            resp = client.post("/v1/chat/completions", json=dict(CHAT_BODY), headers=AUTH_HEADER)

        assert resp.status_code == 200
        call_kwargs = mock_batch_handler.handle_request.call_args
        sent_body = call_kwargs.kwargs["request_body"]
        # force override applied
        assert sent_body["service_tier"] == "flex"
        # original fields preserved
        assert sent_body["model"] == "gpt-4o-mini"

    def test_responses_passthrough_with_override(
        self,
        key_lookup: dict[str, ApiKeyEntry],
        auth_dep: Any,
        batch_proxy_handler: BatchProxyHandler,
        passthrough_handler: PassthroughHandler,
    ) -> None:
        routes, handlers = _build_config_3(batch_proxy_handler, passthrough_handler)
        app = _make_app(routes, handlers, key_lookup, auth_dep)

        upstream_resp = _mock_httpx_response(json_body={"id": "resp-1", "object": "response"})

        with patch("openai_batch_proxy.modes.passthrough.handler.httpx.AsyncClient") as MockClient:
            mock_client_instance = AsyncMock()
            mock_client_instance.request = AsyncMock(return_value=upstream_resp)
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client_instance

            with TestClient(app) as client:
                resp = client.post(
                    "/v1/responses",
                    json={"model": "o3-mini", "input": "think hard"},
                    headers=AUTH_HEADER,
                )

        assert resp.status_code == 200
        sent_body = json.loads(mock_client_instance.request.call_args.kwargs["content"])
        # default override: reasoning.effort applied (not in original)
        assert sent_body["reasoning"]["effort"] == "low"
        # original fields preserved
        assert sent_body["model"] == "o3-mini"

    def test_models_passthrough(
        self,
        key_lookup: dict[str, ApiKeyEntry],
        auth_dep: Any,
        batch_proxy_handler: BatchProxyHandler,
        passthrough_handler: PassthroughHandler,
    ) -> None:
        routes, handlers = _build_config_3(batch_proxy_handler, passthrough_handler)
        app = _make_app(routes, handlers, key_lookup, auth_dep)

        upstream_resp = _mock_httpx_response(json_body={"object": "list", "data": []})

        with patch("openai_batch_proxy.modes.passthrough.handler.httpx.AsyncClient") as MockClient:
            mock_client_instance = AsyncMock()
            mock_client_instance.request = AsyncMock(return_value=upstream_resp)
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client_instance

            with TestClient(app) as client:
                resp = client.get("/v1/models", headers=AUTH_HEADER)

        assert resp.status_code == 200
        call_kwargs = mock_client_instance.request.call_args
        assert call_kwargs.kwargs["url"] == "https://api.openai.com/v1/models"
        assert call_kwargs.kwargs["headers"]["Authorization"] == f"Bearer {TEST_OPENAI_KEY}"
