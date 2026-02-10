import importlib
import logging
import os
import sys
from typing import Final

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from openai_batch_proxy import __version__
from openai_batch_proxy.auth import create_auth_dependency
from openai_batch_proxy.config import AppConfig, load_config
from openai_batch_proxy.errors import register_error_handlers
from openai_batch_proxy.key_config import build_key_lookup, load_api_keys_config
from openai_batch_proxy.routes_dispatch import ModeHandler, create_dispatch_router
from openai_batch_proxy.routes_health import router as health_router

# Configure logging
LOG_LEVEL: Final = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

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

# Discover and validate modes referenced in routes config
modes_needed: set[str] = {r.mode for r in config.routes.values()}

mode_handlers: dict[str, ModeHandler] = {}
app.state.external_redis_client = None

for mode_name in modes_needed:
    # Import the mode's sub-package
    try:
        mod = importlib.import_module(f"openai_batch_proxy.modes.{mode_name}")
    except ModuleNotFoundError:
        logger.critical(f"Unknown mode '{mode_name}' — no sub-package found at modes/{mode_name}/")
        sys.exit(1)

    provider = mod.provider

    # Validate path restrictions
    if provider.supported_paths is not None:
        for path, route_config in config.routes.items():
            if route_config.mode == mode_name and path not in provider.supported_paths:
                logger.critical(
                    f"Mode '{mode_name}' does not support path '{path}'. "
                    f"Supported paths: {sorted(provider.supported_paths)}"
                )
                sys.exit(1)

    # Create the handler, passing mode-specific kwargs
    mode_handlers[mode_name] = provider.create_handler(
        key_lookup=key_lookup,
        redis_config=config.redis,
    )

    # If this mode's provider has an external Redis client, store it for health checks
    if hasattr(provider, "external_redis_client") and provider.external_redis_client is not None:
        app.state.external_redis_client = provider.external_redis_client

# Always register passthrough as the fallback for unmatched paths
if "passthrough" not in mode_handlers:
    from openai_batch_proxy.modes.passthrough import provider as pt_provider

    mode_handlers["passthrough"] = pt_provider.create_handler()

# Register the dispatch router
app.include_router(
    create_dispatch_router(config.routes, mode_handlers, key_lookup, auth_dependency)
)

app.include_router(health_router)

logger.info(f"Server configured: {config.server.host}:{config.server.port}")
logger.info(f"CORS origins: {config.cors.allow_origins}")
logger.info(f"Routes configured: {list(config.routes.keys())}")
logger.info(f"Modes active: {list(mode_handlers.keys())}")


def run() -> None:
    """Run the server using uvicorn."""
    import uvicorn

    uvicorn.run(
        "openai_batch_proxy.main:app",
        host=config.server.host,
        port=config.server.port,
        log_level=LOG_LEVEL.lower(),
    )


if __name__ == "__main__":
    run()
