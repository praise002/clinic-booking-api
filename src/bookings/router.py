import json

from fastapi import APIRouter, Depends, Header, Path, Query, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.bookings.constants import DEFAULT_LIMIT, MAX_LIMIT
from src.bookings.exceptions import InvalidBookingBody
from src.bookings.schemas import BookingListResponse, BookingRequest, BookingResponse
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
    "/bookings",
    response_model=BookingListResponse,
    summary="List a person's bookings",
    description=(
        "That person's bookings, oldest first, cancelled ones included. The email match "
        "ignores case and surrounding spaces. Cursor paging: pass `next_cursor` back as "
        "`cursor` to get the next page; the last page has `next_cursor: null`."
    ),
    responses={
        200: {"description": "A page of bookings."},
        400: error_doc(
            "`email` is missing or blank, `limit` isn't an integer from 1 to 50, or `cursor` "
            "isn't one this API returned.",
            "limit must be an integer from 1 to 50",
            "email is required",
            "cursor is not valid",
        ),
        500: INTERNAL_ERROR_DOC,
    },
)
async def list_bookings(
    # Plain strings, checked in bookings/pipes.py, so every bad value is a 400 with the
    # contract's message; the docs still describe them as their real types.
    email: str = Query(  # type: ignore[assignment]  # None when absent; pipes reject it
        default=None,
        description="Required. Whose bookings to list (case-insensitive).",
        examples=["ada@example.com"],
        json_schema_extra={"format": "email"},
    ),
    limit: str = Query(  # type: ignore[assignment]
        default=None,
        description=f"Page size, an integer from 1 to {MAX_LIMIT}. Default {DEFAULT_LIMIT}.",
        examples=[DEFAULT_LIMIT],
        json_schema_extra={
            "type": "integer",
            "minimum": 1,
            "maximum": MAX_LIMIT,
            "default": DEFAULT_LIMIT,
        },
    ),
    cursor: str = Query(  # type: ignore[assignment]
        default=None, description="`next_cursor` from the previous page. Omit for the first page."
    ),
    session: AsyncSession = Depends(get_session),
):
    return await BookingService(session).list_for_email(email, limit, cursor)


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
