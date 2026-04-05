import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.routing import APIRoute
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.api import api_router
from app.core.config import settings
from app.core.error_schemas import ERROR_RESPONSES, get_openapi_schemas
from app.core.errors import (
    http_exception_handler,
    starlette_http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.core.logger import get_logger
from app.core.middleware import RequestLoggingMiddleware

# Configure logging levels for various loggers
logger = get_logger("main")

# Configure logging levels for third-party libraries to reduce noise
LOGGER_LEVELS = {
    "httpcore.http11": logging.WARNING,
    "httpcore.connection": logging.WARNING,
    "httpx": logging.WARNING,
    "uvicorn.access": logging.WARNING,  # Disable default uvicorn request logging (we use our custom logger)
    "sqlalchemy.engine": logging.WARNING,
}

for logger_name, level in LOGGER_LEVELS.items():
    logging.getLogger(logger_name).setLevel(level)


def custom_generate_unique_id(route: APIRoute) -> str:
    return f"{route.tags[0] if route.tags else 'default'}-{route.name}"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:  # noqa: ARG001
    """Application lifespan: seed notification types on startup, run reminder poller."""
    import asyncio
    import signal

    from app.core.db import async_session
    from app.core.sse import sse_manager
    from app.logic.notifications.reminder_poller import run_reminder_poller
    from app.logic.notifications.seeder import seed_notification_types

    async with async_session() as session:
        await seed_notification_types(session)
    logger.info("Notification types seeded")

    # Register signal handlers so SSE connections close BEFORE uvicorn
    # waits for tasks to complete (lifespan teardown runs too late).
    original_handlers: dict[int, Any] = {}
    for sig in (signal.SIGINT, signal.SIGTERM):
        original_handlers[sig] = signal.getsignal(sig)

        def _handler(
            signum: int, frame: Any, _orig: Any = original_handlers[sig]
        ) -> None:
            sse_manager.shutdown_event.set()
            # Re-raise to uvicorn's original handler so shutdown continues
            if callable(_orig):
                _orig(signum, frame)

        signal.signal(sig, _handler)

    # Start reminder poller as a background task
    poller_task = asyncio.create_task(run_reminder_poller())

    yield

    # Also signal here as a fallback (e.g. programmatic shutdown)
    await sse_manager.shutdown()

    # Cancel reminder poller
    poller_task.cancel()
    try:
        await poller_task
    except asyncio.CancelledError:
        pass

    # Restore original signal handlers
    for sig, handler in original_handlers.items():
        signal.signal(sig, handler)


if settings.SENTRY_DSN and settings.ENVIRONMENT != "local":
    import sentry_sdk

    sentry_sdk.init(dsn=str(settings.SENTRY_DSN), enable_tracing=True)


def custom_openapi() -> dict[str, Any]:
    """
    Custom OpenAPI function to add ProblemDetails schema
    This allows us to generate a frontend client with consistent error types
    """
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        routes=app.routes,
    )

    # Add ProblemDetails schema
    if "components" not in openapi_schema:
        openapi_schema["components"] = {}
    if "schemas" not in openapi_schema["components"]:
        openapi_schema["components"]["schemas"] = {}

    # Add error schemas from error_schemas module
    openapi_schema["components"]["schemas"].update(get_openapi_schemas())  # type: ignore[reportUnknownMemberType]

    app.openapi_schema = openapi_schema
    return app.openapi_schema


app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    generate_unique_id_function=custom_generate_unique_id,
    lifespan=lifespan,
)

app.openapi = custom_openapi  # type: ignore[assignment]

# Exception handlers for consistent problem+json responses
app.add_exception_handler(HTTPException, http_exception_handler)  # type: ignore[arg-type]
app.add_exception_handler(StarletteHTTPException, starlette_http_exception_handler)  # type: ignore[arg-type]
app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
app.add_exception_handler(Exception, unhandled_exception_handler)  # type: ignore[arg-type]

# Add request logging middleware (must be added before other middleware)
app.add_middleware(RequestLoggingMiddleware)

# Set all CORS enabled origins
if settings.all_cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.all_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

ERROR_RESPONSES_TYPED: dict[int | str, dict[str, Any]] = ERROR_RESPONSES  # type: ignore[assignment]

app.include_router(
    api_router,
    prefix=settings.API_V1_STR,
    responses=ERROR_RESPONSES_TYPED,
)


if __name__ == "__main__":
    import uvicorn

    logger.info("Starting FastAPI application")

    uvicorn.run(
        "app.main:app",
        host="localhost",
        port=8000,
        reload=True,
        reload_excludes=[".venv"],
    )
