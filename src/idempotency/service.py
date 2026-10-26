from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.idempotency.exceptions import IdempotencyKeyMismatch
from src.idempotency.pipes import body_hash
from src.idempotency.repository import IdempotencyRepository


@dataclass(frozen=True)
class StoredResponse:
    status_code: int
    body: dict[str, Any]


class IdempotencyService:
    """Claim a key, or replay what it already produced. Runs inside the caller's transaction."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.keys = IdempotencyRepository(session)

    async def claim_or_replay(self, key: str, body: dict[str, Any]) -> StoredResponse | None:
        """None: first use, go ahead (and call `store` before committing).
        A StoredResponse: the key was used before with this body; send that back.
        Raises IdempotencyKeyMismatch (422) if it was used with a different body.
        """
        digest = body_hash(body)
        if await self.keys.claim(key, digest):
            return None

        record = await self.keys.get(key)
        # The claim waited for a committed row, which always carries its response; only a
        # /reset in between could remove it.
        if record is None or record.status_code is None or record.response is None:
            raise RuntimeError(f"idempotency key {key!r} has no stored response")
        if record.body_hash != digest:
            raise IdempotencyKeyMismatch()
        return StoredResponse(record.status_code, record.response)

    async def store(self, key: str, response: StoredResponse) -> None:
        await self.keys.store_response(key, response.status_code, response.body)
