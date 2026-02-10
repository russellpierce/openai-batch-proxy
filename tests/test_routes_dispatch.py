"""Tests for the dispatch router."""

from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse, Response
from fastapi.testclient import TestClient

from openai_batch_proxy.key_config import ApiKeyEntry
from openai_batch_proxy.override_proxy.config import (
    OverrideField,
    OverridesConfig,
    RouteConfig,
)
from openai_batch_proxy.routes_dispatch import ModeRequest, create_dispatch_router


@pytest.fixture
def test_key_lookup() -> dict[str, ApiKeyEntry]:
    """Create a test key lookup."""
    return {
        "sk-test-key": ApiKeyEntry(
            caller_key="sk-test-key",
            openai_key="sk-openai-key",
        )
    }


@pytest.fixture
def mock_passthrough_handler() -> AsyncMock:
    """Create a mock passthrough handler."""
    handler = AsyncMock()
    handler.handle = AsyncMock(
        return_value=JSONResponse(content={"mode": "passthrough"})
    )
    return handler


@pytest.fixture
def mock_batch_proxy_handler() -> AsyncMock:
    """Create a mock batch_proxy handler."""
    handler = AsyncMock()
    handler.handle = AsyncMock(
        return_value=JSONResponse(content={"mode": "batch_proxy"})
    )
    return handler


def auth_dependency(api_key: str = "sk-test-key") -> str:
    """Simple auth dependency for testing."""
    return "sk-test-key"


class TestRouteMatching:
    """Tests for route matching in dispatch router."""

    def test_configured_path_delegates_to_correct_mode(
        self,
        test_key_lookup: dict[str, ApiKeyEntry],
        mock_passthrough_handler: AsyncMock,
        mock_batch_proxy_handler: AsyncMock,
    ) -> None:
        """Configured path should delegate to the specified mode handler."""
        routes = {
            "/v1/chat/completions": RouteConfig(mode="batch_proxy"),
        }
        mode_handlers = {
            "passthrough": mock_passthrough_handler,
            "batch_proxy": mock_batch_proxy_handler,
        }

        app = FastAPI()
        router = create_dispatch_router(routes, mode_handlers, test_key_lookup, auth_dependency)
        app.include_router(router)

        with TestClient(app) as client:
            response = client.post(
                "/v1/chat/completions",
                json={"model": "gpt-4", "messages": []},
                headers={"Authorization": "Bearer sk-test-key"},
            )

        assert response.status_code == 200
        assert response.json()["mode"] == "batch_proxy"
        mock_batch_proxy_handler.handle.assert_called_once()

    def test_unconfigured_path_passthroughs(
        self,
        test_key_lookup: dict[str, ApiKeyEntry],
        mock_passthrough_handler: AsyncMock,
        mock_batch_proxy_handler: AsyncMock,
    ) -> None:
        """Unconfigured path should default to passthrough mode."""
        routes = {
            "/v1/chat/completions": RouteConfig(mode="batch_proxy"),
        }
        mode_handlers = {
            "passthrough": mock_passthrough_handler,
            "batch_proxy": mock_batch_proxy_handler,
        }

        app = FastAPI()
        router = create_dispatch_router(routes, mode_handlers, test_key_lookup, auth_dependency)
        app.include_router(router)

        with TestClient(app) as client:
            response = client.post(
                "/v1/models",
                headers={"Authorization": "Bearer sk-test-key"},
            )

        assert response.status_code == 200
        assert response.json()["mode"] == "passthrough"
        mock_passthrough_handler.handle.assert_called_once()


class TestOverrideApplication:
    """Tests for override application in dispatch router."""

    def test_body_overrides_applied_to_handler(
        self,
        test_key_lookup: dict[str, ApiKeyEntry],
    ) -> None:
        """Body overrides should be applied before delegating to handler."""
        captured_request: list[ModeRequest] = []

        async def capture_handler(mr: ModeRequest) -> Response:
            captured_request.append(mr)
            return JSONResponse(content={"received": mr.body})

        mock_handler = AsyncMock()
        mock_handler.handle = capture_handler

        routes = {
            "/v1/chat/completions": RouteConfig(
                mode="passthrough",
                overrides=OverridesConfig(
                    body={
                        "service_tier": OverrideField(value="flex", mode="force"),
                        "temperature": OverrideField(value=0.7, mode="default"),
                    }
                ),
            ),
        }
        mode_handlers = {"passthrough": mock_handler}

        app = FastAPI()
        router = create_dispatch_router(routes, mode_handlers, test_key_lookup, auth_dependency)
        app.include_router(router)

        with TestClient(app) as client:
            response = client.post(
                "/v1/chat/completions",
                json={"model": "gpt-4", "messages": [], "temperature": 0.5},
                headers={"Authorization": "Bearer sk-test-key"},
            )

        assert response.status_code == 200
        assert len(captured_request) == 1
        mr = captured_request[0]
        # force should override
        assert mr.body["service_tier"] == "flex"
        # default should not override existing
        assert mr.body["temperature"] == 0.5
        # original fields preserved
        assert mr.body["model"] == "gpt-4"

    def test_dot_notation_overrides_applied(
        self,
        test_key_lookup: dict[str, ApiKeyEntry],
    ) -> None:
        """Dot notation overrides should create nested structure."""
        captured_request: list[ModeRequest] = []

        async def capture_handler(mr: ModeRequest) -> Response:
            captured_request.append(mr)
            return JSONResponse(content={"received": mr.body})

        mock_handler = AsyncMock()
        mock_handler.handle = capture_handler

        routes = {
            "/v1/responses": RouteConfig(
                mode="passthrough",
                overrides=OverridesConfig(
                    body={
                        "reasoning.effort": OverrideField(value="low", mode="default"),
                    }
                ),
            ),
        }
        mode_handlers = {"passthrough": mock_handler}

        app = FastAPI()
        router = create_dispatch_router(routes, mode_handlers, test_key_lookup, auth_dependency)
        app.include_router(router)

        with TestClient(app) as client:
            response = client.post(
                "/v1/responses",
                json={"model": "gpt-4"},
                headers={"Authorization": "Bearer sk-test-key"},
            )

        assert response.status_code == 200
        mr = captured_request[0]
        assert mr.body["reasoning"]["effort"] == "low"


class TestModeRequestData:
    """Tests for ModeRequest data passed to handlers."""

    def test_mode_request_contains_correct_keys(
        self,
        test_key_lookup: dict[str, ApiKeyEntry],
    ) -> None:
        """ModeRequest should contain both caller_key and openai_key."""
        captured_request: list[ModeRequest] = []

        async def capture_handler(mr: ModeRequest) -> Response:
            captured_request.append(mr)
            return JSONResponse(content={"ok": True})

        mock_handler = AsyncMock()
        mock_handler.handle = capture_handler

        routes = {}
        mode_handlers = {"passthrough": mock_handler}

        app = FastAPI()
        router = create_dispatch_router(routes, mode_handlers, test_key_lookup, auth_dependency)
        app.include_router(router)

        with TestClient(app) as client:
            response = client.post(
                "/v1/chat/completions",
                json={"model": "gpt-4"},
                headers={"Authorization": "Bearer sk-test-key"},
            )

        assert response.status_code == 200
        mr = captured_request[0]
        assert mr.caller_key == "sk-test-key"
        assert mr.openai_key == "sk-openai-key"
        assert mr.endpoint_path == "/v1/chat/completions"
        assert mr.route_config is None  # unconfigured path

    def test_mode_request_includes_route_config(
        self,
        test_key_lookup: dict[str, ApiKeyEntry],
    ) -> None:
        """ModeRequest should include route_config for configured paths."""
        captured_request: list[ModeRequest] = []

        async def capture_handler(mr: ModeRequest) -> Response:
            captured_request.append(mr)
            return JSONResponse(content={"ok": True})

        mock_handler = AsyncMock()
        mock_handler.handle = capture_handler

        routes = {
            "/v1/chat/completions": RouteConfig(mode="passthrough"),
        }
        mode_handlers = {"passthrough": mock_handler}

        app = FastAPI()
        router = create_dispatch_router(routes, mode_handlers, test_key_lookup, auth_dependency)
        app.include_router(router)

        with TestClient(app) as client:
            response = client.post(
                "/v1/chat/completions",
                json={"model": "gpt-4"},
                headers={"Authorization": "Bearer sk-test-key"},
            )

        assert response.status_code == 200
        mr = captured_request[0]
        assert mr.route_config is not None
        assert mr.route_config.mode == "passthrough"


class TestNonJsonBody:
    """Tests for handling non-JSON request bodies."""

    def test_non_json_body_passes_through(
        self,
        test_key_lookup: dict[str, ApiKeyEntry],
    ) -> None:
        """Non-JSON body should pass through with empty body dict."""
        captured_request: list[ModeRequest] = []

        async def capture_handler(mr: ModeRequest) -> Response:
            captured_request.append(mr)
            return JSONResponse(content={"ok": True})

        mock_handler = AsyncMock()
        mock_handler.handle = capture_handler

        routes = {}
        mode_handlers = {"passthrough": mock_handler}

        app = FastAPI()
        router = create_dispatch_router(routes, mode_handlers, test_key_lookup, auth_dependency)
        app.include_router(router)

        with TestClient(app) as client:
            response = client.post(
                "/v1/files",
                content=b"not-json-content",
                headers={
                    "Authorization": "Bearer sk-test-key",
                    "Content-Type": "application/octet-stream",
                },
            )

        assert response.status_code == 200
        mr = captured_request[0]
        assert mr.body == {}  # body dict empty for non-JSON
