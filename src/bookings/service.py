from typing import Any
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.bookings.exceptions import BookingNotFound
from src.bookings.repository import BookingRepository
from src.bookings.schemas import BookingResponse
from src.slots.exceptions import SlotNotFound
from src.slots.repository import SlotRepository


class BookingService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.bookings = BookingRepository(session)
        self.slots = SlotRepository(session)

    async def create(self, body: dict[str, Any]) -> BookingResponse:
        """The booking pipeline. Validation (Level 2) and the 409 mapping (Level 3) come later."""
        slot_id, name, email = body.get("slot_id"), body.get("name"), body.get("email")

        if await self.slots.get(slot_id) is None:
            raise SlotNotFound()

        booking = await self.bookings.insert(slot_id, name, email)
        await self.session.commit()
        return BookingResponse.from_model(booking)

    async def get(self, booking_id: str) -> BookingResponse:
        # A non-UUID id can't match any booking, so it is a 404 like any unknown id.
        try:
            parsed_id = uuid.UUID(booking_id)
        except ValueError:
            raise BookingNotFound() from None

        booking = await self.bookings.get(parsed_id)
        if booking is None:
            raise BookingNotFound()
        return BookingResponse.from_model(booking)
