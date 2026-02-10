import redis.asyncio as aioredis


class RedisStore:
    """Async Redis wrapper for retry buffer and batch tracking."""

    def __init__(self, redis_client: aioredis.Redis, namespace: str) -> None:
        self._redis = redis_client
        self._ns = namespace

    def _key(self, kind: str, identifier: str) -> str:
        return f"{self._ns}:{kind}:{identifier}"

    async def get_retry_buffer(self, caller_key: str, request_hash: str) -> bytes | None:
        """Check retry buffer for cached response."""
        key = self._key("retry", f"{caller_key}:{request_hash}")
        result: bytes | None = await self._redis.get(key)
        return result

    async def set_retry_buffer(
        self, caller_key: str, request_hash: str, response: bytes, ttl_seconds: int
    ) -> None:
        """Store response in retry buffer with TTL."""
        key = self._key("retry", f"{caller_key}:{request_hash}")
        await self._redis.set(key, response, ex=ttl_seconds)

    async def delete_retry_buffer(self, caller_key: str, request_hash: str) -> None:
        """Invalidate retry buffer entry after successful delivery."""
        key = self._key("retry", f"{caller_key}:{request_hash}")
        await self._redis.delete(key)

    async def store_batch_id(self, request_id: str, batch_id: str) -> None:
        """Track batch ID for a request (for cancellation)."""
        key = self._key("batch", request_id)
        await self._redis.set(key, batch_id, ex=86400)  # 24h safety TTL

    async def get_batch_id(self, request_id: str) -> str | None:
        """Retrieve batch ID for cancellation."""
        key = self._key("batch", request_id)
        result: bytes | None = await self._redis.get(key)
        return result.decode() if result else None
