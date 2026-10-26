from datetime import UTC, datetime
from typing import Any
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.bookings.exceptions import BookingAlreadyCancelled, BookingNotFound, SlotStarted
from src.bookings.models import Booking
from src.bookings.pipes import (
    Cursor,
    decode_cursor,
    encode_cursor,
    parse_limit,
    parse_list_email,
    parse_new_booking,
)
from src.bookings.repository import BookingRepository
from src.bookings.schemas import BookingListResponse, BookingResponse
from src.core.errors import status_for
from src.core.exceptions import BadRequest, Conflict, NotFound
from src.idempotency.service import IdempotencyService, StoredResponse
from src.slots.exceptions import SlotNotFound
from src.slots.repository import SlotRepository

# Outcomes that are final for a request, so an Idempotency-Key replays them. Anything else
# (401, a 500) rolls back, and the key stays free for a real retry.
FINAL_ERRORS = (BadRequest, NotFound, Conflict)


class BookingService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.bookings = BookingRepository(session)
        self.slots = SlotRepository(session)
        self.idempotency = IdempotencyService(session)

    async def create(self, body: dict[str, Any], idempotency_key: str | None) -> StoredResponse:
        """POST /bookings. Returns the status and body to send.

        Without a key, errors are raised as usual. With one, the key is claimed first, and
        the outcome (201 or a final error) is stored on it in the same transaction as the
        booking: both commit together, or neither does.
        """
        if idempotency_key is None:
            booking = await self._book(body)
            await self.session.commit()
            return StoredResponse(201, _booking_body(booking))

        replay = await self.idempotency.claim_or_replay(idempotency_key, body)
        if replay is not None:
            await self.session.rollback()
            return replay

        try:
            booking = await self._book(body)
            outcome = StoredResponse(201, _booking_body(booking))
        except FINAL_ERRORS as error:
            outcome = StoredResponse(status_for(error), {"error": error.message})
        await self.idempotency.store(idempotency_key, outcome)
        await self.session.commit()
        return outcome

    async def _book(self, body: dict[str, Any]) -> Booking:
        """Validate, check the slot, insert. Doesn't commit."""
        new = parse_new_booking(body)

        slot = await self.slots.get(new.slot_id)
        if slot is None:
            raise SlotNotFound()
        # Server UTC time, never the caller's clock.
        if slot.start_at <= datetime.now(UTC):
            raise SlotStarted()

        return await self.bookings.insert(new.slot_id, new.name, new.email)

    async def get(self, booking_id: str) -> BookingResponse:
        booking = await self.bookings.get(_parse_booking_id(booking_id))
        if booking is None:
            raise BookingNotFound()
        return BookingResponse.from_model(booking)

    async def list_for_email(
        self, email: str | None, limit: str | None, cursor: str | None
    ) -> BookingListResponse:
        """One page of a person's bookings. Fetches one extra row to know if there's more."""
        page_size = parse_limit(limit)
        rows = await self.bookings.page_for_email(
            parse_list_email(email), decode_cursor(cursor), page_size + 1
        )
        page, more = rows[:page_size], len(rows) > page_size
        next_cursor = encode_cursor(Cursor(page[-1].created_at, page[-1].id)) if more else None
        return BookingListResponse(
            bookings=[BookingResponse.from_model(b) for b in page], next_cursor=next_cursor
        )

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


def _booking_body(booking: Booking) -> dict[str, Any]:
    return BookingResponse.from_model(booking).model_dump(mode="json")


def _parse_booking_id(booking_id: str) -> uuid.UUID:
    # A non-UUID id can't match any booking, so it is a 404 like any unknown id.
    try:
        return uuid.UUID(booking_id)
    except ValueError:
        raise BookingNotFound() from None
