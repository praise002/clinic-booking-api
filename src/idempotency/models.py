from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class IdempotencyKey(Base):
    """One Idempotency-Key and the final response it produced. Kept until /reset."""

    __tablename__ = "idempotency_keys"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    body_hash: Mapped[str] = mapped_column(Text)
    # Set in the same transaction as the booking, before it commits.
    status_code: Mapped[int | None] = mapped_column(Integer)
    # JSON, not JSONB: JSONB re-sorts keys, and a replay must match the first response
    # byte for byte (migration 0002).
    response: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
