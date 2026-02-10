import json
from typing import Any

import httpx
from fastapi.responses import Response

from openai_batch_proxy.routes_dispatch import ModeRequest


class PassthroughHandler:
    """Handler that proxies requests directly to OpenAI."""

    async def handle(self, mr: ModeRequest) -> Response:
        upstream_headers = {
            "Authorization": f"Bearer {mr.openai_key}",
            "Content-Type": mr.headers.get("content-type", "application/json"),
        }
        content = json.dumps(mr.body).encode() if mr.body else await mr.request.body()

        async with httpx.AsyncClient() as client:
            resp = await client.request(
                method=mr.request.method,
                url=f"https://api.openai.com{mr.endpoint_path}",
                headers=upstream_headers,
                content=content,
                params=mr.query,
            )
        excluded = {"transfer-encoding", "connection", "content-encoding"}
        resp_headers = {k: v for k, v in resp.headers.items() if k.lower() not in excluded}
        return Response(content=resp.content, status_code=resp.status_code, headers=resp_headers)


class Provider:
    """Provider for passthrough mode."""

    supported_paths: frozenset[str] | None = None  # works on any path

    def create_handler(self, **kwargs: Any) -> PassthroughHandler:
        return PassthroughHandler()
