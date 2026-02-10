import logging
from typing import Final

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger: Final = logging.getLogger(__name__)


class ErrorDetail(BaseModel):
    """OpenAI-compatible error detail."""

    message: str
    type: str
    code: str


class ErrorResponse(BaseModel):
    """OpenAI-compatible error response."""

    error: ErrorDetail


class OpenAICompatibleError(Exception):
    """Base exception for OpenAI-compatible errors."""

    def __init__(
        self,
        message: str,
        error_type: str,
        error_code: str,
        status_code: int,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.error_type = error_type
        self.error_code = error_code
        self.status_code = status_code


class AuthenticationError(OpenAICompatibleError):
    """Raised when API key authentication fails."""

    def __init__(self, message: str, error_code: str = "invalid_api_key") -> None:
        super().__init__(
            message=message,
            error_type="authentication_error",
            error_code=error_code,
            status_code=401,
        )


class InvalidRequestError(OpenAICompatibleError):
    """Raised when request is malformed or invalid."""

    def __init__(self, message: str, error_code: str = "invalid_request") -> None:
        super().__init__(
            message=message,
            error_type="invalid_request_error",
            error_code=error_code,
            status_code=400,
        )


class BatchProxyError(OpenAICompatibleError):
    """Raised for batch proxy-specific errors."""

    def __init__(self, message: str, error_code: str = "batch_proxy_error") -> None:
        super().__init__(
            message=message,
            error_type="invalid_request_error",
            error_code=error_code,
            status_code=400,
        )


def _create_error_response(
    status_code: int,
    message: str,
    error_type: str,
    error_code: str,
) -> JSONResponse:
    """Create a JSON response in OpenAI error format."""
    response = ErrorResponse(
        error=ErrorDetail(
            message=message,
            type=error_type,
            code=error_code,
        )
    )
    return JSONResponse(status_code=status_code, content=response.model_dump())


async def openai_compatible_error_handler(
    _request: Request,
    exc: OpenAICompatibleError,
) -> JSONResponse:
    """Handle OpenAI-compatible errors."""
    if exc.status_code >= 500:
        logger.error("%s: %s", exc.error_type, exc.message, exc_info=True)
    else:
        logger.warning("%s: %s", exc.error_type, exc.message)
    return _create_error_response(
        status_code=exc.status_code,
        message=exc.message,
        error_type=exc.error_type,
        error_code=exc.error_code,
    )


async def validation_error_handler(
    _request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Handle Pydantic validation errors in OpenAI format."""
    errors = exc.errors()
    message = "; ".join(f"{'.'.join(str(loc) for loc in e['loc'])}: {e['msg']}" for e in errors)
    logger.warning("Validation error: %s", message)
    return _create_error_response(
        status_code=400,
        message=message,
        error_type="invalid_request_error",
        error_code="validation_error",
    )


async def unhandled_error_handler(
    _request: Request,
    exc: Exception,
) -> JSONResponse:
    """Catch-all for any unhandled exception."""
    logger.error("Unhandled exception: %s", exc, exc_info=exc)
    return _create_error_response(
        status_code=500,
        message="Internal server error",
        error_type="internal_error",
        error_code="internal_error",
    )


def register_error_handlers(app: FastAPI) -> None:
    """Register all error handlers with the FastAPI application."""
    app.add_exception_handler(OpenAICompatibleError, openai_compatible_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_error_handler)  # type: ignore[arg-type]
