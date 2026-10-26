from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from src.bookings.router import router as bookings_router
from src.core.auth import HEALTH_PATH, UNAUTHORIZED_MESSAGE, ApiKeyMiddleware
from src.core.errors import register_global_error_handlers
from src.core.schemas import error_doc
from src.slots.router import router as slots_router

DESCRIPTION = """
Book clinic appointment slots: list slots, book one, and look a booking up.

Implements the Koya Cohort 4 Task 1 contract. Everything is JSON, and every error
response is `{"error": "<message>"}`.

Every endpoint except `GET /health` needs the `X-API-Key` header; without it the API
answers `401`. To try endpoints from this page, press **Authorize** and enter the key.
"""

TAGS = [
    {"name": "slots", "description": "The clinic's appointment slots."},
    {"name": "bookings", "description": "Booking slots and looking bookings up."},
    {"name": "health", "description": "Liveness check for the host. No key needed."},
]

API_KEY_SCHEME = {"ApiKeyAuth": {"type": "apiKey", "in": "header", "name": "X-API-Key"}}
UNAUTHORIZED_DOC = error_doc("`X-API-Key` is missing or wrong.", UNAUTHORIZED_MESSAGE)


def build_openapi(app: FastAPI) -> dict:
    """The generated schema, adjusted to what the API really does:

    - FastAPI documents a 422 "Validation Error" on every route with inputs, but bad input is
      a 400 here (`core/errors.py`); that entry is dropped (a 422 we declare ourselves stays).
    - The key check is middleware, which FastAPI can't see; every route but /health gets the
      `X-API-Key` security requirement and its 401.
    """
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
        tags=app.openapi_tags,
    )
    components = schema.setdefault("components", {})
    components["securitySchemes"] = API_KEY_SCHEME
    for name in ("HTTPValidationError", "ValidationError"):
        components.get("schemas", {}).pop(name, None)

    unauthorized = {
        "description": UNAUTHORIZED_DOC["description"],
        "content": {
            "application/json": {
                "schema": {"$ref": "#/components/schemas/ErrorResponse"},
                **UNAUTHORIZED_DOC["content"]["application/json"],
            }
        },
    }
    for path, operations in schema["paths"].items():
        for operation in operations.values():
            responses = operation.setdefault("responses", {})
            if responses.get("422", {}).get("description") == "Validation Error":
                del responses["422"]
            if path != HEALTH_PATH:
                operation["security"] = [{"ApiKeyAuth": []}]
                responses["401"] = unauthorized
            operation["responses"] = dict(sorted(responses.items()))
    app.openapi_schema = schema
    return schema


def create_app() -> FastAPI:
    app = FastAPI(
        title="Clinic Booking API",
        version="0.1.0",
        description=DESCRIPTION,
        openapi_tags=TAGS,
        # `/bookings/` is a 404 like any unknown path, not a redirect: a redirect has no
        # {"error"} body, and behind a TLS proxy it would point at http://.
        redirect_slashes=False,
        # Swagger keeps the key entered under Authorize across page reloads.
        swagger_ui_parameters={"persistAuthorization": True},
    )
    register_global_error_handlers(app)
    app.add_middleware(ApiKeyMiddleware)

    @app.get(
        "/health",
        tags=["health"],
        summary="Health check",
        description="Returns 200 when the API is up. The only route that needs no API key.",
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
    app.openapi = lambda: build_openapi(app)  # type: ignore[method-assign]
    return app


app = create_app()
