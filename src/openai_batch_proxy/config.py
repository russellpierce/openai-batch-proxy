import logging
import sys
from pathlib import Path
from typing import Final

import yaml
from pydantic import BaseModel, Field

from openai_batch_proxy.override_proxy.config import RouteConfig

logger: Final = logging.getLogger(__name__)


class ServerConfig(BaseModel):
    """Server binding configuration."""

    host: str = "0.0.0.0"
    port: int = Field(default=8000, ge=1, le=65535)


class AuthConfig(BaseModel):
    """Authentication configuration."""

    api_keys_file: str


class CorsConfig(BaseModel):
    """CORS configuration."""

    allow_origins: list[str] = Field(default_factory=lambda: ["*"])


class RedisConfig(BaseModel):
    """Redis connection configuration."""

    url: str = "redis://localhost:6379/0"
    namespace: str = "batch_proxy"


class AppConfig(BaseModel):
    """Complete application configuration."""

    server: ServerConfig = Field(default_factory=ServerConfig)
    auth: AuthConfig
    cors: CorsConfig = Field(default_factory=CorsConfig)
    routes: dict[str, RouteConfig] = Field(default_factory=dict)
    redis: RedisConfig | None = None


def load_config(config_path: str | Path) -> AppConfig:
    """
    Load and validate configuration from YAML file.

    Exits the process with error message if configuration is invalid.
    """
    path = Path(config_path)

    if not path.exists():
        logger.critical(f"Configuration file not found: {path}")
        sys.exit(1)

    logger.info(f"Loading configuration from: {path}")

    with path.open("r") as f:
        raw_config = yaml.safe_load(f)

    if raw_config is None:
        logger.critical(f"Configuration file is empty: {path}")
        sys.exit(1)

    # Let Pydantic validation errors propagate with full details
    config = AppConfig(**raw_config)

    logger.info(f"Configuration loaded: host={config.server.host}, port={config.server.port}")

    return config
