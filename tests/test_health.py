import asyncio
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from openai_batch_proxy.routes_health import router as health_router


@pytest.fixture
def app() -> FastAPI:
    """Create a minimal app with just the health router."""
    app = FastAPI()
    app.include_router(health_router)
    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


def test_health_check_no_external_redis(client: TestClient) -> None:
    """Health returns 200 when no external Redis configured."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "reason": None}


def test_health_check_no_auth_required(client: TestClient) -> None:
    """Health endpoint doesn't require authentication."""
    response = client.get("/health")
    assert response.status_code == 200


def test_health_check_redis_reachable(app: FastAPI) -> None:
    """Health returns 200 when external Redis is configured and reachable."""
    mock_redis = AsyncMock()
    mock_redis.ping.return_value = True
    app.state.external_redis_client = mock_redis

    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "reason": None}
    mock_redis.ping.assert_called_once()


def test_health_check_redis_unreachable(app: FastAPI) -> None:
    """Health returns 503 when external Redis is configured but unreachable."""
    mock_redis = AsyncMock()
    mock_redis.ping.side_effect = ConnectionError("Connection refused")
    app.state.external_redis_client = mock_redis

    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "unhealthy"
    assert data["reason"] == "redis unreachable"


def test_health_check_redis_timeout(app: FastAPI) -> None:
    """Health returns 503 when Redis ping times out."""

    async def slow_ping() -> bool:
        await asyncio.sleep(10)
        return True

    mock_redis = AsyncMock()
    mock_redis.ping.side_effect = slow_ping
    app.state.external_redis_client = mock_redis

    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "unhealthy"
    assert data["reason"] == "redis unreachable"
