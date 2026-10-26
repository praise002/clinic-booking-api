from datetime import datetime

from sqlalchemy import DateTime, Index, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class Slot(Base):
    __tablename__ = "slots"
    __table_args__ = (
        Index("ix_slots_start", "start_at", "id"),
        Index("ix_slots_provider", "provider"),
    )

    # Client-supplied through /reset, e.g. "s1".
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    provider: Mapped[str] = mapped_column(Text)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
