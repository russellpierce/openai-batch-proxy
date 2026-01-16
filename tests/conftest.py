import tempfile
from collections.abc import Generator
from pathlib import Path
from typing import Final

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from skeleton_open_ai.auth import create_auth_dependency, load_api_keys
from skeleton_open_ai.config import AppConfig, AuthConfig, CorsConfig, ServerConfig
from skeleton_open_ai.errors import register_error_handlers
from skeleton_open_ai.routes_chat import create_chat_router
from skeleton_open_ai.routes_health import router as health_router
from skeleton_open_ai.routes_models import create_models_router

TEST_API_KEY: Final = "sk-test-key-12345"
TEST_MODELS: Final = ["test-model", "default_workflow"]


@pytest.fixture
def api_keys_file() -> Generator[Path]:
    """Create a temporary API keys file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write(f"{TEST_API_KEY}\n")
        f.write("# This is a comment\n")
        f.write("\n")  # Empty line
        f.write("sk-another-key\n")
        temp_path = Path(f.name)
    yield temp_path
    temp_path.unlink()


@pytest.fixture
def test_config(api_keys_file: Path) -> AppConfig:
    """Create test configuration."""
    return AppConfig(
        server=ServerConfig(host="127.0.0.1", port=8000),
        auth=AuthConfig(api_keys_file=str(api_keys_file)),
        cors=CorsConfig(allow_origins=["*"]),
        models=list(TEST_MODELS),
    )


@pytest.fixture
def app(test_config: AppConfig, api_keys_file: Path) -> FastAPI:
    """Create test FastAPI application."""
    test_app = FastAPI()

    test_app.add_middleware(
        CORSMiddleware,
        allow_origins=test_config.cors.allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_error_handlers(test_app)

    api_keys = load_api_keys(api_keys_file)
    auth_dependency = create_auth_dependency(api_keys)

    test_app.include_router(health_router)
    test_app.include_router(create_models_router(test_config.models, auth_dependency))
    test_app.include_router(create_chat_router(test_config.models, auth_dependency))

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
