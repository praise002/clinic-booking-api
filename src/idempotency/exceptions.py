from src.core.exceptions import BadRequest, UnprocessableEntity
from src.idempotency.constants import MAX_KEY_LENGTH


class IdempotencyKeyMismatch(UnprocessableEntity):
    message = "Idempotency-Key reused with a different body"


class IdempotencyKeyTooLong(BadRequest):
    message = f"Idempotency-Key must be at most {MAX_KEY_LENGTH} characters"
