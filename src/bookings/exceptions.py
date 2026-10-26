from src.core.exceptions import BadRequest, Conflict, NotFound


class BookingNotFound(NotFound):
    message = "booking not found"


class InvalidBookingBody(BadRequest):
    message = "request body must be a JSON object"


class InvalidBookingField(BadRequest):
    """A missing, empty, non-string or invalid slot_id/name/email. The message names it."""

    message = "invalid booking details"


class SlotStarted(BadRequest):
    message = "slot has already started"


class SlotAlreadyBooked(Conflict):
    message = "slot already booked"


class BookingAlreadyCancelled(Conflict):
    message = "booking already cancelled"
