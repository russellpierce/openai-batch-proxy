from fastapi.testclient import TestClient


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
