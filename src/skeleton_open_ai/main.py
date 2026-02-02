import logging
import os
from typing import Final

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from skeleton_open_ai import __version__
from skeleton_open_ai.auth import create_auth_dependency
from skeleton_open_ai.config import AppConfig, load_config
from skeleton_open_ai.errors import register_error_handlers
from skeleton_open_ai.key_config import build_key_lookup, load_api_keys_config
from skeleton_open_ai.routes_health import router as health_router

# Configure logging
LOG_LEVEL: Final = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)

logger: Final = logging.getLogger(__name__)

# Load configuration
CONFIG_PATH: Final = os.environ.get("CONFIG_PATH", "config.yaml")
config: AppConfig = load_config(CONFIG_PATH)

# Load API keys (unified format for both modes)
keys_config = load_api_keys_config(config.auth.api_keys_file)
key_lookup = build_key_lookup(keys_config)
auth_dependency = create_auth_dependency(frozenset(key_lookup.keys()))

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

# Register routes based on workflow mode
if config.workflow == "batch_proxy":
    from skeleton_open_ai.batch.handler import BatchHandler
    from skeleton_open_ai.batch.redis_store import RedisStore
    from skeleton_open_ai.batch.routes_chat import create_batch_chat_router
    from skeleton_open_ai.routes_proxy_passthrough import create_passthrough_router

    redis_client: aioredis.Redis = aioredis.from_url(config.redis.url)  # type: ignore[no-untyped-call]
    redis_store = RedisStore(redis_client, config.redis.namespace)

    batch_handler = BatchHandler(redis_store, key_lookup)
    app.include_router(create_batch_chat_router(batch_handler, redis_store, auth_dependency))
    # Passthrough must come after batch_chat so /v1/chat/completions is matched first
    app.include_router(create_passthrough_router(key_lookup, auth_dependency))

    logger.info("Batch proxy mode enabled")
else:
    from skeleton_open_ai.routes_chat import create_chat_router
    from skeleton_open_ai.routes_models import create_models_router

    app.include_router(create_models_router(config.models, auth_dependency))
    app.include_router(create_chat_router(config.models, auth_dependency))

    logger.info("Workflow mode enabled")

app.include_router(health_router)

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
