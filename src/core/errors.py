import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.core.exceptions import AppError, BadRequest, NotFound

log = logging.getLogger(__name__)

# Most specific first: the first matching class wins.
STATUS_BY_ERROR: list[tuple[type[AppError], int]] = [
    (NotFound, status.HTTP_404_NOT_FOUND),
    (BadRequest, status.HTTP_400_BAD_REQUEST),
]


def error_response(status_code: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": message})


def register_global_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, http_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, internal_error_handler)


async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    for error_class, status_code in STATUS_BY_ERROR:
        if isinstance(exc, error_class):
            return error_response(status_code, exc.message)
    return error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, exc.message)


async def validation_error_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    # The contract has no 422 for bad input: 422 is reserved for Idempotency-Key reuse.
    first = exc.errors()[0]
    if first["type"] == "json_invalid":
        return error_response(status.HTTP_400_BAD_REQUEST, "request body is not valid JSON")
    field = ".".join(str(part) for part in first["loc"] if part != "body")
    message = first["msg"] if not field else f"{field}: {first['msg']}"
    return error_response(status.HTTP_400_BAD_REQUEST, message)


async def http_error_handler(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
    # Unknown routes (404) and wrong methods (405) keep the {"error": ...} shape.
    return error_response(exc.status_code, str(exc.detail).lower())


async def internal_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    log.exception("unhandled error", exc_info=exc)
    return error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "internal server error")
