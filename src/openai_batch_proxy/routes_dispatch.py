import contextlib
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Final, Protocol

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from openai_batch_proxy.key_config import ApiKeyEntry
from openai_batch_proxy.override_proxy.config import RouteConfig
from openai_batch_proxy.override_proxy.engine import apply_overrides

logger: Final = logging.getLogger(__name__)


@dataclass
class ModeRequest:
    """All data a mode handler receives."""

    request: Request
    endpoint_path: str
    caller_key: str
    openai_key: str
    body: dict[str, Any]
    headers: dict[str, str]
    query: dict[str, str]
    route_config: RouteConfig | None


class ModeHandler(Protocol):
    async def handle(self, mode_request: ModeRequest) -> Response: ...


class ModeProvider(Protocol):
    """What a mode sub-package must expose."""

    supported_paths: frozenset[str] | None

    def create_handler(self, **kwargs: Any) -> ModeHandler: ...


def create_dispatch_router(
    routes: dict[str, RouteConfig],
    mode_handlers: dict[str, ModeHandler],
    key_lookup: dict[str, ApiKeyEntry],
    auth_dependency: Callable[..., str],
) -> APIRouter:
    """Create a dispatch router that routes requests to mode handlers."""
    router = APIRouter(tags=["dispatch"])

    @router.api_route(
        "/v1/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"]
    )
    async def dispatch(
        request: Request,
        path: str,
        api_key: str = Depends(auth_dependency),
    ) -> Response:
        endpoint_path = f"/v1/{path}"
        key_entry = key_lookup[api_key]

        # Look up route config (miss = passthrough, no overrides)
        route_config = routes.get(endpoint_path)
        mode = route_config.mode if route_config else "passthrough"
        logger.debug(
            "Dispatch %s %s → mode=%s caller=%s…%s",
            request.method, endpoint_path, mode,
            api_key[:8], api_key[-4:],
        )

        # Parse body if present
        raw_body = await request.body()
        body: dict[str, Any] = {}
        if raw_body:
            with contextlib.suppress(json.JSONDecodeError, UnicodeDecodeError):
                body = json.loads(raw_body)

        headers = dict(request.headers)
        query = dict(request.query_params)

        # Apply overrides
        if route_config and route_config.overrides:
            body, headers, query = apply_overrides(
                route_config.overrides,
                body,
                headers,
                query,
            )

        # Delegate to mode handler
        handler = mode_handlers[mode]
        return await handler.handle(
            ModeRequest(
                request=request,
                endpoint_path=endpoint_path,
                caller_key=api_key,
                openai_key=key_entry.openai_key,
                body=body,
                headers=headers,
                query=query,
                route_config=route_config,
            )
        )

    return router
