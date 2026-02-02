import logging
from collections.abc import Callable
from typing import Final

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from skeleton_open_ai.key_config import ApiKeyEntry

logger: Final = logging.getLogger(__name__)


def create_passthrough_router(
    key_lookup: dict[str, ApiKeyEntry],
    auth_dependency: Callable[..., str],
) -> APIRouter:
    """Create a generic passthrough router for non-batchable endpoints."""

    router = APIRouter(tags=["passthrough"])

    @router.api_route("/v1/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
    async def proxy_to_openai(
        request: Request,
        path: str,
        api_key: str = Depends(auth_dependency),
    ) -> Response:
        """Relay request to OpenAI API using caller's mapped key."""
        key_entry = key_lookup[api_key]
        async with httpx.AsyncClient() as client:
            resp = await client.request(
                method=request.method,
                url=f"https://api.openai.com/v1/{path}",
                headers={
                    "Authorization": f"Bearer {key_entry.openai_key}",
                    "Content-Type": request.headers.get("Content-Type", "application/json"),
                },
                content=await request.body(),
                params=request.query_params,
            )
        # Filter out hop-by-hop headers
        excluded_headers = {"transfer-encoding", "connection", "content-encoding"}
        headers = {k: v for k, v in resp.headers.items() if k.lower() not in excluded_headers}
        return Response(content=resp.content, status_code=resp.status_code, headers=headers)

    return router
