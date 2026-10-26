from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.schemas import INTERNAL_ERROR_DOC, error_doc
from src.database import get_session
from src.slots.schemas import ResetRequest, ResetResponse, SlotListResponse
from src.slots.service import SlotService

router = APIRouter(tags=["slots"])


@router.post(
    "/reset",
    response_model=ResetResponse,
    summary="Replace all slots",
    description=(
        "Deletes every booking and replaces all slots with the ones sent, including slots "
        "in the past. Runs in one transaction: a rejected request changes nothing."
    ),
    responses={
        200: {"description": "Done. Every booking is gone and the slots are replaced."},
        400: error_doc(
            "The body isn't valid JSON, a slot is missing a field or has a bad value, "
            "or two slots share an id.",
            "slots.0.start: Field required",
        ),
        500: INTERNAL_ERROR_DOC,
    },
)
async def reset(body: ResetRequest, session: AsyncSession = Depends(get_session)):
    await SlotService(session).reset(body)
    return ResetResponse()


@router.get(
    "/slots",
    response_model=SlotListResponse,
    summary="List slots",
    description="Every slot, earliest start first, each with whether it can still be booked.",
    responses={
        200: {"description": "The slots. An empty list when there are none."},
        500: INTERNAL_ERROR_DOC,
    },
)
async def list_slots(
    provider: str | None = Query(
        default=None,
        description="Only this provider's slots (exact, case-sensitive match).",
        examples=["Dr Ade"],
    ),
    session: AsyncSession = Depends(get_session),
):
    return await SlotService(session).list_slots(provider)
