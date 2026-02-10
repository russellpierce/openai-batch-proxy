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

    def create_handler(self, **kwargs: Any) -> BatchProxyHandler:
        key_lookup: dict[str, ApiKeyEntry] = kwargs["key_lookup"]
        redis_config: RedisConfig = kwargs["redis_config"]

        redis_client: aioredis.Redis = aioredis.from_url(redis_config.url)  # type: ignore[no-untyped-call]
        redis_store = RedisStore(redis_client, redis_config.namespace)
        batch_handler = BatchHandler(redis_store, key_lookup)

        return BatchProxyHandler(batch_handler, redis_store)
