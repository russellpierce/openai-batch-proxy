from fastapi.testclient import TestClient


def test_chat_completion_success(client: TestClient, auth_headers: dict[str, str]) -> None:
    """Test successful chat completion."""
    response = client.post(
        "/v1/chat/completions",
        headers=auth_headers,
        json={"model": "test-model", "messages": [{"role": "user", "content": "Hello!"}]},
    )
    assert response.status_code == 200

    data = response.json()
    assert data["object"] == "chat.completion"
    assert data["model"] == "test-model"
    assert len(data["choices"]) == 1
    assert data["choices"][0]["message"]["role"] == "assistant"
    assert data["choices"][0]["finish_reason"] == "stop"
    assert "id" in data
    assert "created" in data


def test_chat_completion_no_auth(client: TestClient) -> None:
    """Test chat completion without authentication fails."""
    response = client.post(
        "/v1/chat/completions",
        json={"model": "test-model", "messages": [{"role": "user", "content": "Hello!"}]},
    )
    assert response.status_code == 401


def test_chat_completion_invalid_model(client: TestClient, auth_headers: dict[str, str]) -> None:
    """Test chat completion with unknown model fails."""
    response = client.post(
        "/v1/chat/completions",
        headers=auth_headers,
        json={
            "model": "nonexistent-model",
            "messages": [{"role": "user", "content": "Hello!"}],
        },
    )
    assert response.status_code == 400

    data = response.json()
    assert data["error"]["code"] == "model_not_found"


def test_chat_completion_empty_messages(client: TestClient, auth_headers: dict[str, str]) -> None:
    """Test chat completion with empty messages fails validation."""
    response = client.post(
        "/v1/chat/completions",
        headers=auth_headers,
        json={"model": "test-model", "messages": []},
    )
    assert response.status_code == 400


def test_chat_completion_usage_is_zero(client: TestClient, auth_headers: dict[str, str]) -> None:
    """Test that usage stats are returned as zeros."""
    response = client.post(
        "/v1/chat/completions",
        headers=auth_headers,
        json={"model": "test-model", "messages": [{"role": "user", "content": "Hello!"}]},
    )
    assert response.status_code == 200

    usage = response.json()["usage"]
    assert usage["prompt_tokens"] == 0
    assert usage["completion_tokens"] == 0
    assert usage["total_tokens"] == 0
