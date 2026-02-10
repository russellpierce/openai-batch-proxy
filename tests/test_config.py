import tempfile
from pathlib import Path

import pytest

from openai_batch_proxy.config import AppConfig, AuthConfig, ServerConfig, load_config


def test_load_valid_config() -> None:
    """Test loading a valid configuration file."""
    config_content = """
server:
  host: "0.0.0.0"
  port: 8080
auth:
  api_keys_file: "keys.txt"
cors:
  allow_origins:
    - "*"
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
        f.write(config_content)
        temp_path = Path(f.name)

    try:
        config = load_config(temp_path)
        assert config.server.host == "0.0.0.0"
        assert config.server.port == 8080
        assert config.auth.api_keys_file == "keys.txt"
    finally:
        temp_path.unlink()


def test_load_config_missing_file() -> None:
    """Test that missing config file causes exit."""
    with pytest.raises(SystemExit):
        load_config("/nonexistent/path/config.yml")


def test_config_invalid_port_rejected() -> None:
    """Test that invalid port is rejected."""
    with pytest.raises(ValueError):
        AppConfig(
            server=ServerConfig(port=99999),
            auth=AuthConfig(api_keys_file="keys.txt"),
        )


def test_config_routes_default_to_empty() -> None:
    """Test that routes default to empty dict."""
    config = AppConfig(auth=AuthConfig(api_keys_file="keys.txt"))
    assert config.routes == {}
