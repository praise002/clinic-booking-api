"""Tests run against a real Postgres: the compose db, in a separate `clinic_test` database.

Start it with `make up_d` (or `docker compose up -d db`) before `make tests`.
"""

import asyncio
from collections.abc import AsyncGenerator
import os

from dotenv import dotenv_values
from sqlalchemy.engine import make_url

# Before any src import: the app's engine must point at the test database.
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL") or dotenv_values(".env").get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://clinic:clinic@localhost:5452/clinic_test"
)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["REDIS_URL"] = os.environ.get("TEST_REDIS_URL") or dotenv_values(".env").get(
    "TEST_REDIS_URL", "redis://localhost:6396/15"
)
# A fixed key, so tests never depend on (or leak) the developer's real one.
API_KEY = "test-api-key"
os.environ["API_KEY"] = API_KEY

from alembic import command
from alembic.config import Config
import asyncpg
from httpx import ASGITransport, AsyncClient
import pytest
from sqlalchemy import text

from src.database import engine
from src.main import app
from src.ratelimit import constants as ratelimit_constants
from src.redis_client import redis_client


async def _create_test_database() -> None:
    url = make_url(TEST_DATABASE_URL)
    conn = await asyncpg.connect(
        user=url.username,
        password=url.password,
        host=url.host,
        port=url.port,
        database="postgres",
    )
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", url.database)
        if not exists:
            await conn.execute(f'CREATE DATABASE "{url.database}"')
    finally:
        await conn.close()


@pytest.fixture(scope="session", autouse=True)
def test_database() -> None:
    """Create the test database once and build the schema with the real migrations."""
    asyncio.run(_create_test_database())
    command.upgrade(Config("alembic.ini"), "head")


@pytest.fixture(autouse=True)
async def clean_tables(test_database) -> AsyncGenerator[None]:
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE idempotency_keys, bookings, slots CASCADE"))
    await redis_client.flushdb()
    yield


@pytest.fixture(autouse=True)
def rate_limit(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Only Level 5 tests (marked `real_rate_limit`) run with the real 5-per-minute limit;
    elsewhere one email books many times in a row (paging, idempotency, concurrency)."""
    if request.node.get_closest_marker("real_rate_limit") is None:
        monkeypatch.setattr(ratelimit_constants, "LIMIT", 10_000)


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient]:
    """A caller with the API key, like Koya's checks."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"X-API-Key": API_KEY},
    ) as ac:
        yield ac


@pytest.fixture
async def anon_client() -> AsyncGenerator[AsyncClient]:
    """A caller with no API key."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
