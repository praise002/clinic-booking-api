from typing import Annotated

from pydantic import AfterValidator, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def use_asyncpg(url: str) -> str:
    """Railway (and most hosts) hand out postgres:// or postgresql:// URLs; the app's
    engine needs the asyncpg driver named in the scheme."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+asyncpg://" + url[len(prefix) :]
    return url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: Annotated[str, AfterValidator(use_asyncpg)]
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30
    REDIS_URL: str = "redis://localhost:6396/0"
    # Every request except GET /health must send this as X-API-Key.
    API_KEY: str = Field(min_length=1)


settings = Settings()
