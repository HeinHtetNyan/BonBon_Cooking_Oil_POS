"""
FastAPI application factory and lifespan.

Startup order:
1. Configure logging (must be first — everything below logs)
2. Initialize database engine + connection pool
3. Initialize Redis connections
4. Register exception handlers
5. Register middleware (order matters — outermost runs first)
6. Mount API router

Shutdown order:
1. Close Redis connections
2. Dispose database engine (drains pool)
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

from app.core.config import settings
from app.core.exceptions import AppError
from app.core.logging import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan manager."""
    logger.info("app.startup", env=settings.APP_ENV, version=settings.APP_VERSION)

    # Initialize database
    from app.database.session import db_manager

    db_manager.init(settings.database_url)
    logger.info("app.database_ready")

    # Initialize Redis
    from app.database.redis import redis_manager

    redis_manager.init()
    logger.info("app.redis_ready")

    yield

    # Shutdown
    logger.info("app.shutdown")
    await redis_manager.close()
    await db_manager.close()
    logger.info("app.shutdown_complete")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        debug=settings.APP_DEBUG,
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        openapi_url="/openapi.json" if not settings.is_production else None,
        default_response_class=ORJSONResponse,
        lifespan=lifespan,
    )

    _register_middleware(app)
    _register_exception_handlers(app)
    _register_routers(app)

    return app


def _register_middleware(app: FastAPI) -> None:
    # CORS — must be registered before custom middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "X-Process-Time"],
    )

    # Custom middleware (applied in reverse order — last registered = outermost)
    from app.middleware.timing import TimingMiddleware
    from app.middleware.request_id import RequestIDMiddleware
    from app.middleware.audit import AuditLogMiddleware
    from app.middleware.idempotency import IdempotencyMiddleware

    app.add_middleware(IdempotencyMiddleware)
    app.add_middleware(AuditLogMiddleware)
    app.add_middleware(TimingMiddleware)
    app.add_middleware(RequestIDMiddleware)


def _register_exception_handlers(app: FastAPI) -> None:
    from pydantic import ValidationError as PydanticValidationError
    from app.common.schemas.base import ErrorDetail, ErrorResponse

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> ORJSONResponse:
        logger.warning(
            "app.handled_error",
            error_code=exc.error_code,
            message=exc.message,
            path=request.url.path,
        )
        return ORJSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(
                error=ErrorDetail(
                    code=exc.error_code,
                    message=exc.message,
                    context=exc.context,
                )
            ).model_dump(),
        )

    @app.exception_handler(PydanticValidationError)
    async def pydantic_error_handler(
        request: Request, exc: PydanticValidationError
    ) -> ORJSONResponse:
        return ORJSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=ErrorResponse(
                error=ErrorDetail(
                    code="validation_error",
                    message="Request validation failed",
                    context={"errors": exc.errors()},
                )
            ).model_dump(),
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> ORJSONResponse:
        logger.exception(
            "app.unhandled_error",
            error=str(exc),
            path=request.url.path,
        )
        return ORJSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                error=ErrorDetail(
                    code="internal_error",
                    message="An unexpected error occurred",
                )
            ).model_dump(),
        )


def _register_routers(app: FastAPI) -> None:
    from fastapi import APIRouter

    from app.modules.auth.routes import router as auth_router
    from app.modules.users.routes import router as users_router

    v1 = APIRouter(prefix="/api/v1")
    v1.include_router(auth_router)
    v1.include_router(users_router)

    # Phase 2 domain routers
    from app.modules.customers.routes import router as customers_router
    from app.modules.inventory.routes import router as inventory_router
    from app.modules.production.routes import router as production_router

    v1.include_router(customers_router)
    v1.include_router(inventory_router)
    v1.include_router(production_router)

    # Phase 2 — Expenses, Audit, Reporting
    from app.modules.expenses.routes import router as expenses_router
    from app.modules.audit.routes import router as audit_router
    from app.modules.reporting.routes import router as reporting_router

    v1.include_router(expenses_router)
    v1.include_router(audit_router)
    v1.include_router(reporting_router)

    # Finance module (Phase 2 — double-entry ledger, debts, payment methods)
    from app.modules.finance.routes import router as finance_router

    v1.include_router(finance_router)

    # Voucher transaction engine
    from app.modules.vouchers.routes import router as vouchers_router

    v1.include_router(vouchers_router)

    app.include_router(v1)

    # Health check (no auth, no versioning)
    @app.get("/health", tags=["Health"], include_in_schema=False)
    async def health_check() -> ORJSONResponse:
        from app.database.session import db_manager
        from app.database.redis import redis_manager

        db_ok = False
        redis_ok = False

        try:
            async with db_manager.connect() as conn:
                await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
            db_ok = True
        except Exception:
            pass

        redis_ok = await redis_manager.ping()

        healthy = db_ok and redis_ok
        return ORJSONResponse(
            status_code=200 if healthy else 503,
            content={
                "status": "healthy" if healthy else "degraded",
                "version": settings.APP_VERSION,
                "checks": {"database": db_ok, "redis": redis_ok},
            },
        )


app = create_app()
