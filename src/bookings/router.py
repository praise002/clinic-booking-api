import json

from fastapi import APIRouter, Depends, Path, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.bookings.exceptions import InvalidBookingBody
from src.bookings.schemas import BookingRequest, BookingResponse
from src.bookings.service import BookingService
from src.core.exceptions import BadRequest
from src.core.schemas import INTERNAL_ERROR_DOC, error_doc
from src.database import get_session

router = APIRouter(tags=["bookings"])

BOOKING_NOT_FOUND_DOC = error_doc(
    "No booking with that id (an id that isn't a UUID is also 404).", "booking not found"
)


@router.post(
    "/bookings",
    status_code=status.HTTP_201_CREATED,
    response_model=BookingResponse,
    summary="Book a slot",
    description=(
        "Creates a confirmed booking for the slot. `name` is stored trimmed and `email` "
        "trimmed and lower case. `slot_id` must name an existing slot that hasn't started."
    ),
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": BookingRequest.model_json_schema()}},
        }
    },
    responses={
        201: {"description": "Booked. The booking, with status `confirmed`."},
        400: error_doc(
            "The body isn't a JSON object; `slot_id`, `name` or `email` is missing, empty or "
            "not a string; the email isn't valid; or the slot has already started.",
            "email is not valid",
            "name is required",
            "slot_id must be a string",
            "slot has already started",
            "request body is not valid JSON",
            "request body must be a JSON object",
        ),
        404: error_doc("The slot doesn't exist.", "slot not found"),
        409: error_doc(
            "The slot already has a confirmed booking. Holds under simultaneous requests: "
            "Postgres allows one confirmed booking per slot, so exactly one of them wins.",
            "slot already booked",
        ),
        500: INTERNAL_ERROR_DOC,
    },
)
async def create_booking(request: Request, session: AsyncSession = Depends(get_session)):
    # The body is parsed by hand, not by a pydantic model: validation failures must be 400
    # with a contract message, and idempotency (Level 4) hashes the parsed body as sent.
    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise BadRequest("request body is not valid JSON") from None
    if not isinstance(body, dict):
        raise InvalidBookingBody()
    return await BookingService(session).create(body)


@router.get(
    "/bookings/{booking_id}",
    response_model=BookingResponse,
    summary="Get a booking",
    description="Looks up one booking by its id, whatever its status.",
    responses={
        200: {"description": "The booking."},
        404: BOOKING_NOT_FOUND_DOC,
        500: INTERNAL_ERROR_DOC,
    },
)
async def get_booking(
    booking_id: str = Path(description="The booking id returned when it was created."),
    session: AsyncSession = Depends(get_session),
):
    return await BookingService(session).get(booking_id)
