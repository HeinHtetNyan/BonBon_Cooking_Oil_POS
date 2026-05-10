"""
Application configuration via pydantic-settings.

All settings are loaded from environment variables (or .env file).
Settings are validated at startup — a misconfigured environment fails fast.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any

from pydantic import AnyHttpUrl, BeforeValidator, Field, PostgresDsn, RedisDsn, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def _parse_list(v: Any) -> list[str]:
    """Accept JSON array string or actual list from env vars."""
    if isinstance(v, list):
        return v
    if isinstance(v, str):
        import json

        try:
            parsed = json.loads(v)
            if isinstance(parsed, list):
                return [str(i) for i in parsed]
        except json.JSONDecodeError:
            return [i.strip() for i in v.split(",") if i.strip()]
    return []


StringList = Annotated[list[str], BeforeValidator(_parse_list)]


class AppEnvironment(StrEnum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TESTING = "testing"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    APP_ENV: AppEnvironment = AppEnvironment.DEVELOPMENT
    APP_NAME: str = "Bon Bon Oil ERP"
    APP_VERSION: str = "0.1.0"
    APP_DEBUG: bool = False
    SECRET_KEY: str = Field(min_length=32)
    ALLOWED_HOSTS: StringList = ["localhost", "127.0.0.1"]
    ALLOWED_ORIGINS: StringList = ["http://localhost:3000", "http://localhost:5173"]

    # PostgreSQL
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "bonbon_oil_db"
    POSTGRES_USER: str = "bonbon_user"
    POSTGRES_PASSWORD: str
    POSTGRES_POOL_SIZE: int = 10
    POSTGRES_MAX_OVERFLOW: int = 20
    POSTGRES_POOL_TIMEOUT: int = 30
    POSTGRES_ECHO: bool = False

    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = ""
    REDIS_DB: int = 0
    REDIS_CACHE_DB: int = 1

    # JWT
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    JWT_ISSUER: str = "bonbon-oil-erp"

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"
    LOG_FILE_PATH: str | None = None

    # Pagination
    DEFAULT_PAGE_SIZE: int = 25
    MAX_PAGE_SIZE: int = 500

    # Multi-tenant (future)
    TENANT_ID: str = "default"

    # Derived properties

    @property
    def database_url(self) -> str:
        """Async PostgreSQL DSN for asyncpg driver."""
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def database_url_sync(self) -> str:
        """Sync PostgreSQL DSN for Alembic migrations."""
        return (
            f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def redis_url(self) -> str:
        auth = f":{self.REDIS_PASSWORD}@" if self.REDIS_PASSWORD else ""
        return f"redis://{auth}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    @property
    def redis_cache_url(self) -> str:
        auth = f":{self.REDIS_PASSWORD}@" if self.REDIS_PASSWORD else ""
        return f"redis://{auth}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_CACHE_DB}"

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == AppEnvironment.PRODUCTION

    @property
    def is_development(self) -> bool:
        return self.APP_ENV == AppEnvironment.DEVELOPMENT

    @property
    def is_testing(self) -> bool:
        return self.APP_ENV == AppEnvironment.TESTING

    @model_validator(mode="after")
    def _validate_production_security(self) -> "Settings":
        if self.is_production and self.SECRET_KEY == "CHANGE_ME_use_openssl_rand_hex_32_in_production":
            raise ValueError("SECRET_KEY must be changed in production")
        if self.is_production and self.APP_DEBUG:
            raise ValueError("APP_DEBUG must be False in production")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings singleton — loaded once at startup."""
    return Settings()  # type: ignore[call-arg]


# Convenience alias for import
settings = get_settings()
