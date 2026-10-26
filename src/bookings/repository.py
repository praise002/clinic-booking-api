import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.bookings.enums import BookingStatus
from src.bookings.models import Booking


class BookingRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def insert(self, slot_id: str, name: str, email: str) -> Booking:
        """Insert a confirmed booking. Caller commits."""
        booking = Booking(slot_id=slot_id, name=name, email=email, status=BookingStatus.CONFIRMED)
        self.session.add(booking)
        await self.session.flush()
        return booking

    async def get(self, booking_id: uuid.UUID) -> Booking | None:
        return await self.session.get(Booking, booking_id)
