import logging
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Final

from fastapi import Request

from skeleton_open_ai.errors import AuthenticationError

logger: Final = logging.getLogger(__name__)


def load_api_keys(filepath: str | Path) -> frozenset[str]:
    """
    Load API keys from file.

    Keys are one per line. Blank lines and lines starting with # are ignored.
    Exits if file doesn't exist or contains no valid keys.
    """
    path = Path(filepath)

    if not path.exists():
        logger.critical(f"API keys file not found: {path}")
        sys.exit(1)

    keys: set[str] = set()

    with path.open("r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                keys.add(line)

    if not keys:
        logger.critical(f"No valid API keys found in: {path}")
        sys.exit(1)

    logger.info(f"Loaded {len(keys)} API key(s)")
    return frozenset(keys)


def create_auth_dependency(valid_keys: frozenset[str]) -> Callable[[Request], str]:
    """
    Create a FastAPI dependency that validates API key authentication.

    Returns a dependency function that extracts and validates the API key
    from the Authorization header.
    """

    def verify_api_key(request: Request) -> str:
        """Verify API key from Authorization header. Returns the key if valid."""
        auth_header: str | None = request.headers.get("Authorization")

        if auth_header is None:
            raise AuthenticationError(
                message="Missing Authorization header", error_code="missing_auth_header"
            )

        if not auth_header.startswith("Bearer "):
            raise AuthenticationError(
                message="Invalid Authorization header format. Expected: Bearer <api_key>",
                error_code="invalid_auth_format",
            )

        api_key = auth_header[7:]  # Remove "Bearer " prefix

        if api_key not in valid_keys:
            raise AuthenticationError(message="Invalid API key", error_code="invalid_api_key")

        return api_key

    return verify_api_key
