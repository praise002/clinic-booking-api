from sqlalchemy.ext.asyncio import AsyncSession

from src.ratelimit import service as ratelimit
from src.slots.repository import SlotRepository
from src.slots.schemas import ResetRequest, SlotListResponse, SlotResponse


class SlotService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.slots = SlotRepository(session)

    async def reset(self, request: ResetRequest) -> None:
        """One transaction: either every slot is replaced, or nothing changes. Then every
        email's rate-limit count starts again."""
        await self.slots.replace_all(request.slots)
        await self.session.commit()
        await ratelimit.clear_all()

    async def list_slots(self, provider: str | None) -> SlotListResponse:
        rows = await self.slots.list_with_availability(provider)
        return SlotListResponse(
            slots=[
                SlotResponse(
                    id=slot.id,
                    provider=slot.provider,
                    start=slot.start_at,
                    end=slot.end_at,
                    available=available,
                )
                for slot, available in rows
            ]
        )
