import tempfile
from collections.abc import Generator
from pathlib import Path
from typing import Final
from unittest.mock import AsyncMock

import pytest

from openai_batch_proxy.config import AppConfig, AuthConfig, CorsConfig, RedisConfig, ServerConfig
from openai_batch_proxy.key_config import ApiKeyEntry, ApiKeysConfig, build_key_lookup

TEST_API_KEY: Final = "sk-test-key-12345"
TEST_OPENAI_KEY: Final = "sk-openai-test-key"


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
        redis=RedisConfig(),
    )


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
