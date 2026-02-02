import tempfile
from collections.abc import Generator
from pathlib import Path
from typing import Final
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from skeleton_open_ai.auth import create_auth_dependency, load_api_keys
from skeleton_open_ai.config import AppConfig, AuthConfig, CorsConfig, RedisConfig, ServerConfig
from skeleton_open_ai.errors import register_error_handlers
from skeleton_open_ai.key_config import ApiKeyEntry, ApiKeysConfig, build_key_lookup
from skeleton_open_ai.routes_chat import create_chat_router
from skeleton_open_ai.routes_health import router as health_router
from skeleton_open_ai.routes_models import create_models_router

TEST_API_KEY: Final = "sk-test-key-12345"
TEST_OPENAI_KEY: Final = "sk-openai-test-key"
TEST_MODELS: Final = ["test-model", "default_workflow"]


@pytest.fixture
def api_keys_file() -> Generator[Path]:
    """Create a temporary API keys file (legacy txt format)."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write(f"{TEST_API_KEY}\n")
        f.write("# This is a comment\n")
        f.write("\n")  # Empty line
        f.write("sk-another-key\n")
        temp_path = Path(f.name)
    yield temp_path
    temp_path.unlink()


@pytest.fixture
def api_keys_yaml_file() -> Generator[Path]:
    """Create a temporary api_keys.yaml file."""
    content = f"""keys:
  - caller_key: "{TEST_API_KEY}"
    openai_key: "{TEST_OPENAI_KEY}"
    retry_buffer_ttl_seconds: 3600
  - caller_key: "sk-another-key"
    openai_key: "sk-openai-another"
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(content)
        temp_path = Path(f.name)
    yield temp_path
    temp_path.unlink()


@pytest.fixture
def test_api_keys_config() -> ApiKeysConfig:
    """Create test API keys config."""
    return ApiKeysConfig(
        keys=[
            ApiKeyEntry(
                caller_key=TEST_API_KEY,
                openai_key=TEST_OPENAI_KEY,
                retry_buffer_ttl_seconds=3600,
            ),
            ApiKeyEntry(
                caller_key="sk-another-key",
                openai_key="sk-openai-another",
            ),
        ]
    )


@pytest.fixture
def test_key_lookup(test_api_keys_config: ApiKeysConfig) -> dict[str, ApiKeyEntry]:
    """Create test key lookup dict."""
    return build_key_lookup(test_api_keys_config)


@pytest.fixture
def test_config(api_keys_yaml_file: Path) -> AppConfig:
    """Create test configuration."""
    return AppConfig(
        server=ServerConfig(host="127.0.0.1", port=8000),
        auth=AuthConfig(api_keys_file=str(api_keys_yaml_file)),
        cors=CorsConfig(allow_origins=["*"]),
        models=list(TEST_MODELS),
        redis=RedisConfig(),
    )


@pytest.fixture
def app(api_keys_file: Path) -> FastAPI:
    """Create test FastAPI application (workflow mode)."""
    test_app = FastAPI()

    test_app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_error_handlers(test_app)

    api_keys = load_api_keys(api_keys_file)
    auth_dependency = create_auth_dependency(api_keys)

    test_app.include_router(health_router)
    test_app.include_router(create_models_router(list(TEST_MODELS), auth_dependency))
    test_app.include_router(create_chat_router(list(TEST_MODELS), auth_dependency))

    return test_app


@pytest.fixture
def client(app: FastAPI) -> Generator[TestClient]:
    """Create test client."""
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """Return valid authentication headers."""
    return {"Authorization": f"Bearer {TEST_API_KEY}"}


@pytest.fixture
def mock_redis_store() -> AsyncMock:
    """Create a mock RedisStore."""
    store = AsyncMock()
    store.get_retry_buffer = AsyncMock(return_value=None)
    store.set_retry_buffer = AsyncMock()
    store.delete_retry_buffer = AsyncMock()
    store.store_batch_id = AsyncMock()
    store.get_batch_id = AsyncMock(return_value=None)
    return store


@pytest.fixture
def mock_openai_client() -> AsyncMock:
    """Create a mock OpenAI batch client."""
    client = AsyncMock()
    client.check_model_supports_batch = AsyncMock(return_value=True)
    client.submit_batch = AsyncMock(return_value="batch_test_123")
    client.poll_batch = AsyncMock(
        return_value={
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "created": 1234567890,
            "model": "gpt-4o-mini",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "Hello!"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }
    )
    client.cancel_batch = AsyncMock(return_value="cancelling")
    client.sync_call = AsyncMock(
        return_value={
            "id": "chatcmpl-sync",
            "object": "chat.completion",
            "created": 1234567890,
            "model": "gpt-4o-mini",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "Hello sync!"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }
    )
    return client
