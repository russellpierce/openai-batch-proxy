from fastapi.testclient import TestClient

from tests.conftest import TEST_MODELS


def test_list_models_success(client: TestClient, auth_headers: dict[str, str]) -> None:
    """Test listing models with valid authentication."""
    response = client.get("/v1/models", headers=auth_headers)
    assert response.status_code == 200

    data = response.json()
    assert data["object"] == "list"
    assert len(data["data"]) == len(TEST_MODELS)

    model_ids = [m["id"] for m in data["data"]]
    for model in TEST_MODELS:
        assert model in model_ids


def test_list_models_no_auth(client: TestClient) -> None:
    """Test listing models without authentication fails."""
    response = client.get("/v1/models")
    assert response.status_code == 401
    assert "error" in response.json()


def test_list_models_invalid_auth(client: TestClient) -> None:
    """Test listing models with invalid key fails."""
    response = client.get("/v1/models", headers={"Authorization": "Bearer invalid-key"})
    assert response.status_code == 401
