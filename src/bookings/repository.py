import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.bookings.enums import BookingStatus
from src.bookings.exceptions import SlotAlreadyBooked
from src.bookings.models import Booking

# The partial unique index that allows one confirmed booking per slot (migration 0001).
ONE_CONFIRMED_PER_SLOT = "uq_bookings_slot_confirmed"


def _violated_constraint(error: IntegrityError) -> str | None:
    # SQLAlchemy wraps the driver error; asyncpg's own exception names the constraint.
    return getattr(error.orig.__cause__, "constraint_name", None)


class BookingRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def insert(self, slot_id: str, name: str, email: str) -> Booking:
        """Insert a confirmed booking. Caller commits.

        There is no "is the slot free?" check first: that check and the insert would be two
        steps, and two requests could both pass the check. Postgres decides instead. When
        two inserts race, the second waits on the first's index entry; once the first
        commits, the second fails on `uq_bookings_slot_confirmed`, which becomes a 409.

        The insert runs in a SAVEPOINT, so a refusal rolls back only this insert and the
        rest of the transaction (Level 4's idempotency record) stays usable.
        """
        booking = Booking(slot_id=slot_id, name=name, email=email, status=BookingStatus.CONFIRMED)
        try:
            async with self.session.begin_nested():
                self.session.add(booking)
        except IntegrityError as error:
            if _violated_constraint(error) == ONE_CONFIRMED_PER_SLOT:
                raise SlotAlreadyBooked() from None
            raise
        return booking

    async def get(self, booking_id: uuid.UUID) -> Booking | None:
        return await self.session.get(Booking, booking_id)
