import tempfile
from pathlib import Path

import pytest

from skeleton_open_ai.config import AppConfig, AuthConfig, ServerConfig, load_config


def test_load_valid_config() -> None:
    """Test loading a valid configuration file."""
    config_content = """
server:
  host: "0.0.0.0"
  port: 8080
auth:
  api_keys_file: "keys.txt"
models:
  - model1
  - model2
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
        assert config.models == ["model1", "model2"]
    finally:
        temp_path.unlink()


def test_load_config_missing_file() -> None:
    """Test that missing config file causes exit."""
    with pytest.raises(SystemExit):
        load_config("/nonexistent/path/config.yml")


def test_config_empty_models_rejected() -> None:
    """Test that empty models list is rejected."""
    with pytest.raises(ValueError, match="models"):
        AppConfig(auth=AuthConfig(api_keys_file="keys.txt"), models=[])


def test_config_invalid_port_rejected() -> None:
    """Test that invalid port is rejected."""
    with pytest.raises(ValueError):
        AppConfig(
            server=ServerConfig(port=99999),
            auth=AuthConfig(api_keys_file="keys.txt"),
            models=["model1"],
        )
