import base64
from dataclasses import dataclass
from datetime import datetime
from typing import Any
import uuid

from email_validator import EmailNotValidError, validate_email

from src.bookings.constants import DEFAULT_LIMIT, MAX_LIMIT
from src.bookings.exceptions import InvalidBookingField, InvalidListQuery

REQUIRED_FIELDS = ("slot_id", "name", "email")


@dataclass(frozen=True)
class NewBooking:
    slot_id: str
    name: str
    email: str


def _required_string(body: dict[str, Any], field: str) -> str:
    value = body.get(field)
    if value is None:
        raise InvalidBookingField(f"{field} is required")
    if not isinstance(value, str):
        raise InvalidBookingField(f"{field} must be a string")
    if not value.strip():
        raise InvalidBookingField(f"{field} is required")
    return value


def parse_new_booking(body: dict[str, Any]) -> NewBooking:
    """Validate a POST /bookings body. Name is stored trimmed; email trimmed and lower case.

    The slot id is used exactly as sent (the contract only trims name and email).
    """
    slot_id, name, email = (_required_string(body, field) for field in REQUIRED_FIELDS)
    email = email.strip().lower()
    try:
        # Syntax only: no DNS lookups on the request path.
        validate_email(email, check_deliverability=False)
    except EmailNotValidError:
        raise InvalidBookingField("email is not valid") from None
    return NewBooking(slot_id=slot_id, name=name.strip(), email=email)


# ── GET /bookings query ──────────────────────────────────────────────────────

LIMIT_MESSAGE = f"limit must be an integer from 1 to {MAX_LIMIT}"


def parse_list_email(raw: str | None) -> str:
    """Matched like stored emails: trimmed and lower case."""
    if raw is None or not raw.strip():
        raise InvalidListQuery("email is required")
    return raw.strip().lower()


def parse_limit(raw: str | None) -> int:
    if raw is None:
        return DEFAULT_LIMIT
    # Digits only: "1.5", "-1", " 5" and "" are all rejected, not rounded or trimmed.
    if not raw.isascii() or not raw.isdigit() or not 1 <= int(raw) <= MAX_LIMIT:
        raise InvalidListQuery(LIMIT_MESSAGE)
    return int(raw)


@dataclass(frozen=True)
class Cursor:
    """A position in one person's bookings: the last (created_at, id) already returned."""

    created_at: datetime
    booking_id: uuid.UUID


def encode_cursor(cursor: Cursor) -> str:
    raw = f"{cursor.created_at.isoformat()}|{cursor.booking_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_cursor(token: str | None) -> Cursor | None:
    """None when absent; anything that isn't a cursor this API made is a 400."""
    if token is None:
        return None
    try:
        raw = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)).decode()
        created_at, booking_id = raw.split("|")
        parsed = Cursor(datetime.fromisoformat(created_at), uuid.UUID(booking_id))
    except ValueError:  # bad base64, not UTF-8, wrong shape, bad date or bad UUID
        raise InvalidListQuery("cursor is not valid") from None
    if parsed.created_at.tzinfo is None:
        raise InvalidListQuery("cursor is not valid")
    return parsed
