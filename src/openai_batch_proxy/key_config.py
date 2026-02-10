import logging
import sys
from pathlib import Path
from typing import Final

import yaml
from pydantic import BaseModel, Field

logger: Final = logging.getLogger(__name__)


class ApiKeyEntry(BaseModel):
    """Single API key mapping with per-key configuration."""

    caller_key: str
    openai_key: str = ""
    retry_buffer_ttl_seconds: int = Field(default=86400, ge=0)


class ApiKeysConfig(BaseModel):
    """Root configuration from api_keys.yaml."""

    keys: list[ApiKeyEntry] = Field(min_length=1)


def load_api_keys_config(filepath: str | Path) -> ApiKeysConfig:
    """Load and validate api_keys.yaml. Exits on error."""
    path = Path(filepath)

    if not path.exists():
        logger.critical(f"API keys file not found: {path}")
        sys.exit(1)

    logger.info(f"Loading API keys from: {path}")

    with path.open("r") as f:
        raw = yaml.safe_load(f)

    if raw is None:
        logger.critical(f"API keys file is empty: {path}")
        sys.exit(1)

    config = ApiKeysConfig(**raw)
    logger.info(f"Loaded {len(config.keys)} API key mapping(s)")
    return config


def build_key_lookup(config: ApiKeysConfig) -> dict[str, ApiKeyEntry]:
    """Build a dict from caller_key -> ApiKeyEntry for O(1) lookup."""
    return {entry.caller_key: entry for entry in config.keys}
