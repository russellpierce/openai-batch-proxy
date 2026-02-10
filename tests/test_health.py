import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from openai_batch_proxy.routes_health import router as health_router


@pytest.fixture
def client() -> TestClient:
    """Create a minimal app with just the health router."""
    app = FastAPI()
    app.include_router(health_router)
    return TestClient(app)


def test_health_check(client: TestClient) -> None:
    """Test health endpoint returns healthy status."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_health_check_no_auth_required(client: TestClient) -> None:
    """Test health endpoint doesn't require authentication."""
    # No Authorization header
    response = client.get("/health")
    assert response.status_code == 200
