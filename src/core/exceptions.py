class AppError(Exception):
    """Base class for every domain error.

    Subclasses set `message`; `core/errors.py` maps each subclass to a status code
    and renders it as {"error": message}. Services raise these, never HTTPException.
    """

    message = "an error occurred"

    def __init__(self, message: str = ""):
        self.message = message or self.__class__.message
        super().__init__(self.message)


class NotFound(AppError):
    message = "not found"


class BadRequest(AppError):
    message = "bad request"


class Conflict(AppError):
    message = "conflict"


class UnprocessableEntity(AppError):
    """422. The contract keeps 422 for one case only: an Idempotency-Key reused with a
    different body. Bad input is a 400 (see core/errors.py)."""

    message = "unprocessable entity"
