"""Hosting: database URLs from Neon (and other hosts) become working asyncpg settings."""

import pytest

from src.config import use_asyncpg
from src.db_options import engine_options

NEON_DIRECT = (
    "postgresql://app:pw@ep-cool-sun-123456.us-east-1.aws.neon.tech/neondb"
    "?sslmode=require&channel_binding=require"
)
NEON_POOLED = (
    "postgresql://app:pw@ep-cool-sun-123456-pooler.us-east-1.aws.neon.tech/neondb"
    "?sslmode=require&channel_binding=require"
)


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("postgres://u:p@h:5432/db", "postgresql+asyncpg://u:p@h:5432/db"),
        ("postgresql://u:p@h:5432/db", "postgresql+asyncpg://u:p@h:5432/db"),
        ("postgresql+asyncpg://u:p@h:5432/db", "postgresql+asyncpg://u:p@h:5432/db"),
    ],
)
def test_host_database_urls_get_the_asyncpg_driver(given: str, expected: str):
    assert use_asyncpg(given) == expected


def test_neon_ssl_parameters_become_asyncpg_ssl():
    # asyncpg rejects libpq's sslmode/channel_binding URL parameters.
    url, connect_args = engine_options(use_asyncpg(NEON_DIRECT))

    assert url.drivername == "postgresql+asyncpg"
    assert "sslmode" not in url.query and "channel_binding" not in url.query
    assert connect_args["ssl"] == "require"


def test_a_direct_neon_connection_keeps_statement_caching():
    _, connect_args = engine_options(use_asyncpg(NEON_DIRECT))

    assert "statement_cache_size" not in connect_args


def test_the_neon_pooler_turns_off_prepared_statement_caching():
    # Neon's pooler (PgBouncer, transaction mode) can't keep a connection's prepared
    # statements between transactions, so asyncpg's and SQLAlchemy's caches are off and
    # every prepared statement gets a unique name.
    url, connect_args = engine_options(use_asyncpg(NEON_POOLED))

    assert connect_args["statement_cache_size"] == 0
    assert url.query["prepared_statement_cache_size"] == "0"
    name = connect_args["prepared_statement_name_func"]
    assert name() != name()


def test_a_plain_local_url_is_unchanged():
    url, connect_args = engine_options("postgresql+asyncpg://clinic:clinic@localhost:5452/clinic")

    assert url.render_as_string(hide_password=False) == (
        "postgresql+asyncpg://clinic:clinic@localhost:5452/clinic"
    )
    assert connect_args == {}
