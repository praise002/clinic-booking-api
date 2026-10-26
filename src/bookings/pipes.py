from dataclasses import dataclass
from typing import Any

from email_validator import EmailNotValidError, validate_email

from src.bookings.exceptions import InvalidBookingField

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
