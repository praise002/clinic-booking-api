from sqlalchemy import delete, exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.bookings.enums import BookingStatus
from src.bookings.models import Booking
from src.idempotency.models import IdempotencyKey
from src.slots.models import Slot
from src.slots.schemas import SlotIn


class SlotRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def replace_all(self, slots: list[SlotIn]) -> None:
        """Delete every idempotency record, booking and slot, then insert the new slots.
        Caller commits."""
        await self.session.execute(delete(IdempotencyKey))
        await self.session.execute(delete(Booking))
        await self.session.execute(delete(Slot))
        self.session.add_all(
            Slot(id=s.id, provider=s.provider, start_at=s.start, end_at=s.end) for s in slots
        )
        await self.session.flush()

    async def list_with_availability(self, provider: str | None) -> list[tuple[Slot, bool]]:
        """Slots earliest first, each paired with "has no confirmed booking"."""
        booked = (
            exists()
            .where(Booking.slot_id == Slot.id, Booking.status == BookingStatus.CONFIRMED)
            .correlate(Slot)
        )
        query = select(Slot, ~booked).order_by(Slot.start_at, Slot.id)
        if provider is not None:
            query = query.where(Slot.provider == provider)
        result = await self.session.execute(query)
        return [(slot, available) for slot, available in result.all()]

    async def get(self, slot_id: str) -> Slot | None:
        return await self.session.get(Slot, slot_id)
