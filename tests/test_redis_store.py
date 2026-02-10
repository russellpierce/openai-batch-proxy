import fakeredis.aioredis
import pytest

from openai_batch_proxy.batch.redis_store import RedisStore


@pytest.fixture
async def redis_store() -> RedisStore:
    """Create a RedisStore backed by fakeredis."""
    client = fakeredis.aioredis.FakeRedis()
    return RedisStore(client, namespace="test")


@pytest.mark.asyncio
async def test_retry_buffer_get_miss(redis_store: RedisStore) -> None:
    """Get returns None when key doesn't exist."""
    result = await redis_store.get_retry_buffer("caller1", "hash1")
    assert result is None


@pytest.mark.asyncio
async def test_retry_buffer_set_and_get(redis_store: RedisStore) -> None:
    """Set then get returns the stored value."""
    data = b'{"result": "ok"}'
    await redis_store.set_retry_buffer("caller1", "hash1", data, ttl_seconds=3600)
    result = await redis_store.get_retry_buffer("caller1", "hash1")
    assert result == data


@pytest.mark.asyncio
async def test_retry_buffer_delete(redis_store: RedisStore) -> None:
    """Delete removes the entry."""
    data = b'{"result": "ok"}'
    await redis_store.set_retry_buffer("caller1", "hash1", data, ttl_seconds=3600)
    await redis_store.delete_retry_buffer("caller1", "hash1")
    result = await redis_store.get_retry_buffer("caller1", "hash1")
    assert result is None


@pytest.mark.asyncio
async def test_namespace_isolation() -> None:
    """Different namespaces don't collide."""
    client = fakeredis.aioredis.FakeRedis()
    store_a = RedisStore(client, namespace="ns_a")
    store_b = RedisStore(client, namespace="ns_b")

    await store_a.set_retry_buffer("caller1", "hash1", b"data_a", ttl_seconds=3600)
    result_b = await store_b.get_retry_buffer("caller1", "hash1")
    assert result_b is None

    result_a = await store_a.get_retry_buffer("caller1", "hash1")
    assert result_a == b"data_a"


@pytest.mark.asyncio
async def test_caller_isolation(redis_store: RedisStore) -> None:
    """Different callers don't see each other's entries."""
    await redis_store.set_retry_buffer("caller_a", "hash1", b"data_a", ttl_seconds=3600)
    result = await redis_store.get_retry_buffer("caller_b", "hash1")
    assert result is None


@pytest.mark.asyncio
async def test_batch_id_store_and_get(redis_store: RedisStore) -> None:
    """Store and retrieve batch ID."""
    await redis_store.store_batch_id("req123", "batch_456")
    result = await redis_store.get_batch_id("req123")
    assert result == "batch_456"


@pytest.mark.asyncio
async def test_batch_id_get_miss(redis_store: RedisStore) -> None:
    """Get batch ID returns None when missing."""
    result = await redis_store.get_batch_id("nonexistent")
    assert result is None
