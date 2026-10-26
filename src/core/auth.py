import hmac

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from src.config import settings

# Routes that work without the key: the host's healthcheck, and the API docs (they hold no
# data; trying an endpoint from them needs the key, entered through Swagger's Authorize box).
HEALTH_PATH = "/health"
DOCS_PATHS = {"/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json"}
PUBLIC_PATHS = {HEALTH_PATH, *DOCS_PATHS}
UNAUTHORIZED_MESSAGE = "invalid or missing API key"


class ApiKeyMiddleware:
    """Rejects any request without the right X-API-Key with 401 {"error": ...}.

    It runs before routing, so unknown routes and wrong methods are 401 too,
    and before the body is read, so a caller without the key learns nothing from validation.
    """

    def __init__(self, app: ASGIApp):
        self.app = app
        self.expected = settings.API_KEY.encode()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] in PUBLIC_PATHS:
            await self.app(scope, receive, send)
            return

        sent = dict(scope["headers"]).get(b"x-api-key", b"")
        # Constant-time compare: response timing doesn't reveal how much of a guess matched.
        if not sent or not hmac.compare_digest(sent, self.expected):
            response = JSONResponse(status_code=401, content={"error": UNAUTHORIZED_MESSAGE})
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
