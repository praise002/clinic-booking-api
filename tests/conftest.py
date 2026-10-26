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

from alembic import command
from alembic.config import Config
import asyncpg
from httpx import ASGITransport, AsyncClient
import pytest
from sqlalchemy import text

from src.database import engine
from src.main import app


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
    yield


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
