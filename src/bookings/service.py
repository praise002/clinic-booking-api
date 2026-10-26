from datetime import UTC, datetime
from typing import Any
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.bookings.exceptions import BookingAlreadyCancelled, BookingNotFound, SlotStarted
from src.bookings.pipes import parse_new_booking
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
        """The booking pipeline: validate, check the slot, insert. (409 mapping is Level 3.)"""
        new = parse_new_booking(body)

        slot = await self.slots.get(new.slot_id)
        if slot is None:
            raise SlotNotFound()
        # Server UTC time, never the caller's clock.
        if slot.start_at <= datetime.now(UTC):
            raise SlotStarted()

        booking = await self.bookings.insert(new.slot_id, new.name, new.email)
        await self.session.commit()
        return BookingResponse.from_model(booking)

    async def get(self, booking_id: str) -> BookingResponse:
        booking = await self.bookings.get(_parse_booking_id(booking_id))
        if booking is None:
            raise BookingNotFound()
        return BookingResponse.from_model(booking)

    async def cancel(self, booking_id: str) -> BookingResponse:
        parsed_id = _parse_booking_id(booking_id)
        booking = await self.bookings.cancel(parsed_id)
        if booking is None:
            # Nothing was confirmed under that id: tell "already cancelled" from "unknown".
            if await self.bookings.exists(parsed_id):
                raise BookingAlreadyCancelled()
            raise BookingNotFound()
        await self.session.commit()
        return BookingResponse.from_model(booking)


def _parse_booking_id(booking_id: str) -> uuid.UUID:
    # A non-UUID id can't match any booking, so it is a 404 like any unknown id.
    try:
        return uuid.UUID(booking_id)
    except ValueError:
        raise BookingNotFound() from None
