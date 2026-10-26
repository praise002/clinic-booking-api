from src.core.exceptions import BadRequest, NotFound


class BookingNotFound(NotFound):
    message = "booking not found"


class InvalidBookingBody(BadRequest):
    message = "request body must be a JSON object"
