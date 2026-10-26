from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from src.config import settings
from src.db_options import engine_options

# Per process. A burst of simultaneous bookings (the 50-way proof) queues for a connection
# for up to DB_POOL_TIMEOUT seconds instead of failing. On a serverless host each instance
# has its own pool, so DB_POOL_SIZE/DB_MAX_OVERFLOW are set smaller there.
# pool_pre_ping + pool_recycle: a database that scales to zero (Neon) drops idle
# connections, so each one is checked before use and replaced after 5 minutes.
_url, _connect_args = engine_options(settings.DATABASE_URL)
engine = create_async_engine(
    _url,
    connect_args=_connect_args,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_timeout=settings.DB_POOL_TIMEOUT,
    pool_pre_ping=True,
    pool_recycle=300,
)
async_session = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


async def get_session() -> AsyncGenerator[AsyncSession]:
    async with async_session() as session:
        yield session
