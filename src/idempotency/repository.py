from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.idempotency.models import IdempotencyKey


class IdempotencyRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def claim(self, key: str, body_hash: str) -> bool:
        """Insert the key; True if this request is its first use. Caller commits.

        If another request holds the same key in an open transaction, Postgres makes this
        insert wait on the primary key until that one commits (then: conflict, False) or
        rolls back (then: inserted, True). Two retries can't both get to book.
        """
        result = await self.session.execute(
            insert(IdempotencyKey)
            .values(key=key, body_hash=body_hash)
            .on_conflict_do_nothing(index_elements=[IdempotencyKey.key])
            .returning(IdempotencyKey.key)
        )
        return result.first() is not None

    async def get(self, key: str) -> IdempotencyKey | None:
        result = await self.session.execute(
            select(IdempotencyKey).where(IdempotencyKey.key == key)
        )
        return result.scalar_one_or_none()

    async def store_response(self, key: str, status_code: int, response: dict[str, Any]) -> None:
        await self.session.execute(
            update(IdempotencyKey)
            .where(IdempotencyKey.key == key)
            .values(status_code=status_code, response=response)
        )
