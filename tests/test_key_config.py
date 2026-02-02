import tempfile
from pathlib import Path

import pytest

from skeleton_open_ai.key_config import (
    ApiKeyEntry,
    ApiKeysConfig,
    build_key_lookup,
    load_api_keys_config,
)


def test_load_valid_config() -> None:
    """Valid api_keys.yaml loads successfully."""
    content = """keys:
  - caller_key: "sk-caller-1"
    openai_key: "sk-openai-1"
    retry_buffer_ttl_seconds: 7200
  - caller_key: "sk-caller-2"
    openai_key: "sk-openai-2"
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(content)
        path = Path(f.name)

    try:
        config = load_api_keys_config(path)
        assert len(config.keys) == 2
        assert config.keys[0].caller_key == "sk-caller-1"
        assert config.keys[0].openai_key == "sk-openai-1"
        assert config.keys[0].retry_buffer_ttl_seconds == 7200
        assert config.keys[1].retry_buffer_ttl_seconds == 86400  # default
    finally:
        path.unlink()


def test_load_missing_file() -> None:
    """Missing file causes SystemExit."""
    with pytest.raises(SystemExit):
        load_api_keys_config("/nonexistent/api_keys.yaml")


def test_load_empty_file() -> None:
    """Empty file causes SystemExit."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("")
        path = Path(f.name)
    try:
        with pytest.raises(SystemExit):
            load_api_keys_config(path)
    finally:
        path.unlink()


def test_load_empty_keys_list() -> None:
    """Empty keys list fails validation."""
    content = "keys: []\n"
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(content)
        path = Path(f.name)
    try:
        with pytest.raises(Exception):  # noqa: B017
            load_api_keys_config(path)
    finally:
        path.unlink()


def test_default_ttl() -> None:
    """Default TTL is 86400 seconds."""
    entry = ApiKeyEntry(caller_key="sk-test", openai_key="sk-openai")
    assert entry.retry_buffer_ttl_seconds == 86400


def test_empty_openai_key_allowed() -> None:
    """Empty openai_key is valid (for workflow mode)."""
    entry = ApiKeyEntry(caller_key="sk-test")
    assert entry.openai_key == ""


def test_build_key_lookup() -> None:
    """build_key_lookup creates correct mapping."""
    config = ApiKeysConfig(
        keys=[
            ApiKeyEntry(caller_key="sk-a", openai_key="sk-openai-a"),
            ApiKeyEntry(caller_key="sk-b", openai_key="sk-openai-b"),
        ]
    )
    lookup = build_key_lookup(config)
    assert "sk-a" in lookup
    assert "sk-b" in lookup
    assert lookup["sk-a"].openai_key == "sk-openai-a"
    assert lookup["sk-b"].openai_key == "sk-openai-b"
