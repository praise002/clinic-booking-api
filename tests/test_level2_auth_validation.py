"""Level 2: only requests with the API key get in, and bad bookings are turned away (task-1.md)."""

from httpx import AsyncClient
import pytest

from tests.conftest import API_KEY

FUTURE = {
    "id": "s1",
    "provider": "Dr Ade",
    "start": "2030-01-01T09:00:00Z",
    "end": "2030-01-01T09:30:00Z",
}
PAST = {
    "id": "past",
    "provider": "Dr Ade",
    "start": "2020-01-01T09:00:00Z",
    "end": "2020-01-01T09:30:00Z",
}
BOOKING = {"slot_id": "s1", "name": "Ada Obi", "email": "ada@example.com"}

# Every endpoint except /health, plus a route that doesn't exist.
PROTECTED = [
    ("POST", "/reset"),
    ("GET", "/slots"),
    ("POST", "/bookings"),
    ("GET", "/bookings/00000000-0000-4000-8000-000000000000"),
    ("GET", "/nowhere"),
]


@pytest.fixture
async def slots(client: AsyncClient) -> None:
    response = await client.post("/reset", json={"slots": [FUTURE, PAST]})
    assert response.status_code == 200, response.text


def assert_error(response, status: int, message: str | None = None) -> None:
    assert response.status_code == status, response.text
    body = response.json()
    assert set(body) == {"error"}, body
    assert isinstance(body["error"], str) and body["error"]
    if message is not None:
        assert body["error"] == message


# ── API key ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("method", "path"), PROTECTED)
@pytest.mark.parametrize(
    "headers",
    [{}, {"X-API-Key": "wrong"}, {"X-API-Key": ""}, {"X-API-Key": API_KEY + "x"}],
    ids=["missing", "wrong", "empty", "longer"],
)
async def test_requests_without_the_right_key_are_401(
    anon_client: AsyncClient, method: str, path: str, headers: dict
):
    response = await anon_client.request(method, path, headers=headers, json=BOOKING)

    assert_error(response, 401, "invalid or missing API key")


async def test_a_rejected_key_is_logged_without_the_key_or_query(
    anon_client: AsyncClient, caplog: pytest.LogCaptureFixture
):
    with caplog.at_level("WARNING", logger="src.core.auth"):
        await anon_client.get("/slots?provider=secret-query", headers={"X-API-Key": "guess-123"})
        await anon_client.get("/slots")

    messages = [record.getMessage() for record in caplog.records]
    assert len(messages) == 2
    assert messages[0].startswith("401 GET /slots from ") and messages[0].endswith("(wrong key)")
    assert messages[1].endswith("(missing key)")
    assert not any("guess-123" in m or "secret-query" in m for m in messages)


async def test_health_needs_no_key(anon_client: AsyncClient):
    response = await anon_client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
async def test_the_api_docs_need_no_key(anon_client: AsyncClient, path: str):
    # The docs hold no data; trying an endpoint from them still needs the key.
    response = await anon_client.get(path)

    assert response.status_code == 200


async def test_the_key_is_checked_before_anything_else(anon_client: AsyncClient):
    # A bad body without a key is 401, not 400: callers without the key learn nothing.
    response = await anon_client.post(
        "/bookings", content=b"{not json", headers={"Content-Type": "application/json"}
    )

    assert_error(response, 401)


async def test_a_reset_without_the_key_changes_nothing(
    client: AsyncClient, anon_client: AsyncClient, slots
):
    await anon_client.post("/reset", json={"slots": []}, headers={"X-API-Key": "wrong"})

    assert len((await client.get("/slots")).json()["slots"]) == 2


# ── Booking validation ───────────────────────────────────────────────────────


@pytest.mark.parametrize("field", ["slot_id", "name", "email"])
async def test_a_missing_field_is_400(client: AsyncClient, slots, field: str):
    body = {k: v for k, v in BOOKING.items() if k != field}

    assert_error(await client.post("/bookings", json=body), 400, f"{field} is required")


@pytest.mark.parametrize("field", ["slot_id", "name", "email"])
@pytest.mark.parametrize("value", ["", "   ", None])
async def test_an_empty_field_is_400(client: AsyncClient, slots, field: str, value):
    body = {**BOOKING, field: value}

    assert_error(await client.post("/bookings", json=body), 400, f"{field} is required")


@pytest.mark.parametrize("field", ["slot_id", "name", "email"])
@pytest.mark.parametrize("value", [123, ["ada@example.com"], {"a": 1}, True])
async def test_a_field_that_is_not_a_string_is_400(client: AsyncClient, slots, field, value):
    body = {**BOOKING, field: value}

    assert_error(await client.post("/bookings", json=body), 400, f"{field} must be a string")


@pytest.mark.parametrize(
    "email", ["not-an-email", "ada@", "@example.com", "ada@example", "a b@example.com"]
)
async def test_an_invalid_email_is_400(client: AsyncClient, slots, email: str):
    body = {**BOOKING, "email": email}

    assert_error(await client.post("/bookings", json=body), 400, "email is not valid")


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (b"{not json", "request body is not valid JSON"),
        (b"", "request body is not valid JSON"),
        (b'["s1"]', "request body must be a JSON object"),
        (b'"s1"', "request body must be a JSON object"),
    ],
)
async def test_a_body_that_is_not_a_json_object_is_400(
    client: AsyncClient, slots, content, message
):
    response = await client.post(
        "/bookings", content=content, headers={"Content-Type": "application/json"}
    )

    assert_error(response, 400, message)


async def test_an_unknown_slot_is_404(client: AsyncClient, slots):
    response = await client.post("/bookings", json={**BOOKING, "slot_id": "nope"})

    assert_error(response, 404, "slot not found")


async def test_a_slot_that_has_started_is_400(client: AsyncClient, slots):
    response = await client.post("/bookings", json={**BOOKING, "slot_id": "past"})

    assert_error(response, 400, "slot has already started")


async def test_name_and_email_are_trimmed_and_email_is_lower_cased(client: AsyncClient, slots):
    response = await client.post(
        "/bookings",
        json={"slot_id": "s1", "name": "  Ada Obi \t", "email": "  Ada.Obi@Example.COM  "},
    )

    assert response.status_code == 201, response.text
    booking = response.json()
    assert booking["name"] == "Ada Obi"
    assert booking["email"] == "ada.obi@example.com"
    stored = (await client.get(f"/bookings/{booking['id']}")).json()
    assert (stored["name"], stored["email"]) == ("Ada Obi", "ada.obi@example.com")


async def test_a_rejected_booking_creates_nothing(client: AsyncClient, slots):
    await client.post("/bookings", json={**BOOKING, "email": "not-an-email"})
    await client.post("/bookings", json={**BOOKING, "slot_id": "past"})

    available = {s["id"]: s["available"] for s in (await client.get("/slots")).json()["slots"]}
    assert available == {"past": True, "s1": True}


async def test_the_root_url_redirects_to_the_docs_without_a_key(anon_client: AsyncClient):
    response = await anon_client.get("/")

    assert response.status_code == 307
    assert response.headers["location"] == "/docs"


async def test_the_redirect_is_not_part_of_the_documented_api(client: AsyncClient):
    spec = (await client.get("/openapi.json")).json()

    assert "/" not in spec["paths"]
