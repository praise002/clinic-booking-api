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
