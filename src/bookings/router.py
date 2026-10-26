import json

from fastapi import APIRouter, Depends, Header, Path, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.bookings.exceptions import InvalidBookingBody
from src.bookings.schemas import BookingRequest, BookingResponse
from src.bookings.service import BookingService
from src.core.exceptions import BadRequest
from src.core.schemas import INTERNAL_ERROR_DOC, error_doc
from src.database import get_session
from src.idempotency.constants import MAX_KEY_LENGTH
from src.idempotency.pipes import parse_key

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
        "trimmed and lower case. `slot_id` must name an existing slot that hasn't started.\n\n"
        "**Retries:** send an `Idempotency-Key`. Repeating it with the same body returns the "
        "first response again (same status, same booking id) and never books twice, even "
        "if the repeats arrive at the same moment. Final outcomes are replayed: 201, 400, "
        "404 and 409. Keys are kept until the next `POST /reset`."
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
            f"Idempotency-Key must be at most {MAX_KEY_LENGTH} characters",
        ),
        404: error_doc("The slot doesn't exist.", "slot not found"),
        409: error_doc(
            "The slot already has a confirmed booking. Holds under simultaneous requests: "
            "Postgres allows one confirmed booking per slot, so exactly one of them wins.",
            "slot already booked",
        ),
        422: error_doc(
            "The `Idempotency-Key` was already used with a different body.",
            "Idempotency-Key reused with a different body",
        ),
        500: INTERNAL_ERROR_DOC,
    },
)
async def create_booking(
    request: Request,
    idempotency_key: str | None = Header(
        default=None,
        alias="Idempotency-Key",
        description=(
            f"Optional, at most {MAX_KEY_LENGTH} characters. Makes retries safe: the same key "
            "with the same body returns the first response again. Blank counts as absent."
        ),
        examples=["9f1c6c1e-booking-attempt-1"],
    ),
    session: AsyncSession = Depends(get_session),
):
    key = parse_key(idempotency_key)
    # The body is parsed by hand, not by a pydantic model: validation failures must be 400
    # with a contract message, and idempotency hashes the parsed body as sent.
    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise BadRequest("request body is not valid JSON") from None
    if not isinstance(body, dict):
        raise InvalidBookingBody()
    outcome = await BookingService(session).create(body, key)
    return JSONResponse(status_code=outcome.status_code, content=outcome.body)


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


@router.delete(
    "/bookings/{booking_id}",
    response_model=BookingResponse,
    summary="Cancel a booking",
    description=(
        "Sets the booking's status to `cancelled` and frees the slot, so it can be booked "
        "again. The booking itself is kept. Two simultaneous cancels give one 200 and one 409."
    ),
    responses={
        200: {"description": "The cancelled booking, with status `cancelled`."},
        404: BOOKING_NOT_FOUND_DOC,
        409: error_doc("The booking is already cancelled.", "booking already cancelled"),
        500: INTERNAL_ERROR_DOC,
    },
)
async def cancel_booking(
    booking_id: str = Path(description="The booking id returned when it was created."),
    session: AsyncSession = Depends(get_session),
):
    return await BookingService(session).cancel(booking_id)
