import logging
import os
from typing import Final

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from skeleton_open_ai import __version__
from skeleton_open_ai.auth import create_auth_dependency, load_api_keys
from skeleton_open_ai.config import AppConfig, load_config
from skeleton_open_ai.errors import register_error_handlers
from skeleton_open_ai.routes_chat import create_chat_router
from skeleton_open_ai.routes_health import router as health_router
from skeleton_open_ai.routes_models import create_models_router

# Configure logging
LOG_LEVEL: Final = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)

logger: Final = logging.getLogger(__name__)

# Load configuration
CONFIG_PATH: Final = os.environ.get("CONFIG_PATH", "config.yml")
config: AppConfig = load_config(CONFIG_PATH)

# Load API keys
api_keys = load_api_keys(config.auth.api_keys_file)

# Create FastAPI application
app: Final = FastAPI(
    title="OpenAI-Compatible API",
    description="Custom AI workflow behind an OpenAI-compatible interface",
    version=__version__,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors.allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register error handlers
register_error_handlers(app)

# Create auth dependency
auth_dependency = create_auth_dependency(api_keys)

# Register routes
app.include_router(health_router)
app.include_router(create_models_router(config.models, auth_dependency))
app.include_router(create_chat_router(config.models, auth_dependency))

logger.info(f"Server configured: {config.server.host}:{config.server.port}")
logger.info(f"Available models: {config.models}")
logger.info(f"CORS origins: {config.cors.allow_origins}")


def run() -> None:
    """Run the server using uvicorn."""
    import uvicorn

    uvicorn.run(
        "skeleton_open_ai.main:app",
        host=config.server.host,
        port=config.server.port,
        log_level=LOG_LEVEL.lower(),
    )


if __name__ == "__main__":
    run()
