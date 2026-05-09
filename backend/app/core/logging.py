"""
Structured logging using structlog.

Every log entry is a JSON object in production (human-readable in dev).
Request ID is injected into log context automatically by middleware.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog
from structlog.types import EventDict, WrappedLogger

from app.core.config import settings


def _add_app_info(
    logger: WrappedLogger,
    method_name: str,
    event_dict: EventDict,
) -> EventDict:
    """Inject app name and version into every log entry."""
    event_dict["app"] = settings.APP_NAME
    event_dict["version"] = settings.APP_VERSION
    event_dict["env"] = settings.APP_ENV
    return event_dict


def _drop_color_message_key(
    logger: WrappedLogger,
    method_name: str,
    event_dict: EventDict,
) -> EventDict:
    """Remove uvicorn's color_message duplication."""
    event_dict.pop("color_message", None)
    return event_dict


def configure_logging() -> None:
    """
    Configure structlog for the entire application.

    - JSON output in production/staging
    - Human-readable colored output in development
    - Standard library logging is bridged so uvicorn/sqlalchemy logs flow through
    """
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _add_app_info,
        _drop_color_message_key,
        structlog.processors.StackInfoRenderer(),
    ]

    if settings.LOG_FORMAT == "json" or settings.is_production:
        renderer: Any = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            *shared_processors,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    # File handler (optional) — creates the parent directory if it does not exist.
    # If the directory cannot be created (e.g. permission denied), falls back to
    # stdout-only logging with a warning rather than crashing the process.
    handlers: list[logging.Handler] = [handler]
    if settings.LOG_FILE_PATH:
        import os
        from logging.handlers import RotatingFileHandler

        log_path = settings.LOG_FILE_PATH
        try:
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            file_handler = RotatingFileHandler(
                log_path,
                maxBytes=100 * 1024 * 1024,  # 100 MB
                backupCount=10,
            )
            file_handler.setFormatter(formatter)
            handlers.append(file_handler)
        except OSError as e:
            # Cannot open log file — continue with stdout handler only
            logging.getLogger(__name__).warning(
                "Could not create log file %s (%s). Falling back to stdout logging.",
                log_path,
                e,
            )

    root_logger = logging.getLogger()
    root_logger.handlers = []
    for h in handlers:
        root_logger.addHandler(h)
    root_logger.setLevel(log_level)

    # Tune noisy third-party loggers
    logging.getLogger("uvicorn").setLevel(log_level)
    logging.getLogger("uvicorn.access").setLevel(log_level)
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.DEBUG if settings.POSTGRES_ECHO else logging.WARNING
    )
    logging.getLogger("celery").setLevel(log_level)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
