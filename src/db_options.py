from typing import Any
import uuid

from sqlalchemy.engine import URL, make_url

# Neon's pooled hosts are named ep-<id>-pooler.<region>.aws.neon.tech.
POOLER_HOST_MARKER = "-pooler."
# libpq URL parameters asyncpg doesn't understand.
LIBPQ_ONLY_PARAMS = ("sslmode", "channel_binding")


def _unique_statement_name() -> str:
    return f"__asyncpg_{uuid.uuid4()}__"


def engine_options(database_url: str) -> tuple[URL, dict[str, Any]]:
    """The URL and asyncpg connect_args for a database URL from any host.

    - `sslmode=require` (Neon, most hosts) becomes asyncpg's `ssl="require"`.
    - Behind a transaction-mode pooler (Neon's `-pooler` host, PgBouncer) a connection's
      prepared statements don't survive between transactions, so asyncpg's and
      SQLAlchemy's statement caches are off and each statement gets a unique name.
    """
    url = make_url(database_url)
    query = dict(url.query)
    connect_args: dict[str, Any] = {}

    sslmode = query.get("sslmode")
    for name in LIBPQ_ONLY_PARAMS:
        query.pop(name, None)
    if sslmode and sslmode != "disable":
        connect_args["ssl"] = sslmode

    if url.host and POOLER_HOST_MARKER in url.host:
        connect_args["statement_cache_size"] = 0
        connect_args["prepared_statement_name_func"] = _unique_statement_name
        query["prepared_statement_cache_size"] = "0"

    return url.set(query=query), connect_args
