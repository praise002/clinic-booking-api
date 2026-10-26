from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from src.config import settings

# Per worker process. A burst of simultaneous bookings (the 50-way proof) queues for a
# connection for up to DB_POOL_TIMEOUT seconds instead of failing; with 2 workers that's at
# most 2 × (pool + overflow) = 60 connections, under Postgres's default limit of 100.
engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_timeout=settings.DB_POOL_TIMEOUT,
)
async_session = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


async def get_session() -> AsyncGenerator[AsyncSession]:
    async with async_session() as session:
        yield session
