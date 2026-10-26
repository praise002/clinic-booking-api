from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from src.bookings.router import router as bookings_router
from src.core.errors import register_global_error_handlers
from src.slots.router import router as slots_router

DESCRIPTION = """
Book clinic appointment slots: list slots, book one, and look a booking up.

Implements the Koya Cohort 4 Task 1 contract. Everything is JSON, and every error
response is `{"error": "<message>"}`.
"""

TAGS = [
    {"name": "slots", "description": "The clinic's appointment slots."},
    {"name": "bookings", "description": "Booking slots and looking bookings up."},
    {"name": "health", "description": "Liveness check for the host."},
]


def without_default_422(app: FastAPI) -> dict:
    """FastAPI documents a 422 "Validation Error" on every route with inputs, but bad input
    is a 400 here (`core/errors.py`). Drop that entry; a 422 we declare ourselves stays."""
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
        tags=app.openapi_tags,
    )
    for operations in schema["paths"].values():
        for operation in operations.values():
            responses = operation.get("responses", {})
            if responses.get("422", {}).get("description") == "Validation Error":
                del responses["422"]
    for name in ("HTTPValidationError", "ValidationError"):
        schema.get("components", {}).get("schemas", {}).pop(name, None)
    app.openapi_schema = schema
    return schema


def create_app() -> FastAPI:
    app = FastAPI(
        title="Clinic Booking API",
        version="0.1.0",
        description=DESCRIPTION,
        openapi_tags=TAGS,
    )
    register_global_error_handlers(app)

    @app.get(
        "/health",
        tags=["health"],
        summary="Health check",
        description="Returns 200 when the API is up. Used by the host's healthcheck.",
        responses={
            200: {
                "description": "The API is up.",
                "content": {"application/json": {"example": {"status": "ok"}}},
            }
        },
    )
    async def health():
        return {"status": "ok"}

    app.include_router(slots_router)
    app.include_router(bookings_router)
    app.openapi = lambda: without_default_422(app)  # type: ignore[method-assign]
    return app


app = create_app()
