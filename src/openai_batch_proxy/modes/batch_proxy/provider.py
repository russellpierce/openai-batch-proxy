from typing import Any

import redis.asyncio as aioredis

from openai_batch_proxy.batch.handler import BatchHandler
from openai_batch_proxy.batch.redis_store import RedisStore
from openai_batch_proxy.config import RedisConfig
from openai_batch_proxy.key_config import ApiKeyEntry
from openai_batch_proxy.modes.batch_proxy.handler import BatchProxyHandler


class Provider:
    """Provider for batch_proxy mode."""

    supported_paths: frozenset[str] = frozenset({
        "/v1/chat/completions",
        "/v1/completions",
        "/v1/embeddings",
        "/v1/moderations",
        "/v1/responses",
    })

    _external_redis_client: aioredis.Redis | None = None

    def create_handler(self, **kwargs: Any) -> BatchProxyHandler:
        key_lookup: dict[str, ApiKeyEntry] = kwargs["key_lookup"]
        redis_config: RedisConfig | None = kwargs["redis_config"]

        if redis_config is not None:
            # External Redis — existing behavior
            redis_client: aioredis.Redis = aioredis.from_url(redis_config.url)  # type: ignore[no-untyped-call]
            self._external_redis_client = redis_client
            namespace = redis_config.namespace
        else:
            # Embedded redislite — no external server needed
            import redislite

            self._redislite_instance = redislite.Redis()  # Keep reference to prevent GC
            socket_file = self._redislite_instance.socket_file
            redis_client = aioredis.from_url(f"unix://{socket_file}")  # type: ignore[no-untyped-call]
            self._external_redis_client = None
            namespace = "batch_proxy"

        redis_store = RedisStore(redis_client, namespace)
        batch_handler = BatchHandler(redis_store, key_lookup)

        return BatchProxyHandler(batch_handler, redis_store)

    @property
    def external_redis_client(self) -> aioredis.Redis | None:
        """Return the external Redis client for health checks, or None if using redislite."""
        return self._external_redis_client
