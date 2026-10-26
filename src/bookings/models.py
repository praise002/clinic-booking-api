from datetime import datetime
import uuid

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class Booking(Base):
    __tablename__ = "bookings"
    __table_args__ = (
        CheckConstraint("status IN ('confirmed', 'cancelled')", name="ck_bookings_status"),
        # THE double-booking guarantee: at most one confirmed booking per slot.
        # A cancelled booking drops out of the index, which frees the slot.
        Index(
            "uq_bookings_slot_confirmed",
            "slot_id",
            unique=True,
            postgresql_where=text("status = 'confirmed'"),
        ),
        Index("ix_bookings_email_page", "email", "created_at", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    slot_id: Mapped[str] = mapped_column(Text, ForeignKey("slots.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(Text)
    # Stored trimmed and lower case.
    email: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
