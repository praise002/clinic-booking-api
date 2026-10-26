"""Level 5: at most 5 booking attempts per email per minute, failed ones included (task-1.md)."""

import asyncio
from collections import Counter
import logging

from httpx import AsyncClient
import pytest
from sqlalchemy import text

from src.database import engine
from src.ratelimit import constants as ratelimit_constants

pytestmark = pytest.mark.real_rate_limit

SLOTS = [
    {
        "id": f"s{i}",
        "provider": "Dr Ade",
        "start": f"2030-01-0{i}T09:00:00Z",
        "end": f"2030-01-0{i}T09:30:00Z",
    }
    for i in range(1, 8)
]
TOO_MANY = {"error": "too many booking attempts, try again later"}


@pytest.fixture
async def slots(client: AsyncClient) -> None:
    response = await client.post("/reset", json={"slots": SLOTS})
    assert response.status_code == 200, response.text


def attempt(slot_id: str = "nope", email: str = "ada@example.com", name: str = "Ada") -> dict:
    return {"slot_id": slot_id, "name": name, "email": email}


def assert_429(response) -> None:
    assert response.status_code == 429, response.text
    assert response.json() == TOO_MANY
    retry_after = response.headers["Retry-After"]
    assert retry_after.isdigit(), retry_after
    assert 1 <= int(retry_after) <= 60


async def test_the_sixth_attempt_in_a_minute_is_429(client: AsyncClient, slots):
    for i in range(1, 6):
        response = await client.post("/bookings", json=attempt(f"s{i}"))
        assert response.status_code == 201, response.text

    assert_429(await client.post("/bookings", json=attempt("s6")))


async def test_failed_attempts_count(client: AsyncClient, slots):
    outcomes = [
        (await client.post("/bookings", json=body)).status_code
        for body in (
            attempt("nope"),  # 404
            attempt("s1", name=""),  # 400
            attempt("s1"),  # 201
            attempt("s1"),  # 409
            attempt("nope"),  # 404
        )
    ]
    assert outcomes == [404, 400, 201, 409, 404]

    assert_429(await client.post("/bookings", json=attempt("s2")))


async def test_the_limit_is_per_email_after_trim_and_lower_case(client: AsyncClient, slots):
    for email in (
        "ada@example.com",
        " ADA@example.com",
        "Ada@Example.COM ",
        "ada@EXAMPLE.com",
        "ada@example.com",
    ):
        await client.post("/bookings", json=attempt(email=email))

    assert_429(await client.post("/bookings", json=attempt(email="  ADA@EXAMPLE.COM  ")))


async def test_other_emails_are_not_affected(client: AsyncClient, slots):
    for _ in range(6):
        await client.post("/bookings", json=attempt())

    other = await client.post("/bookings", json=attempt("s1", email="bola@example.com"))

    assert other.status_code == 201


async def test_a_429_is_checked_before_validation_and_creates_nothing(client: AsyncClient, slots):
    for _ in range(5):
        await client.post("/bookings", json=attempt())

    # Over the limit, even a perfect booking is refused, and nothing is booked.
    assert_429(await client.post("/bookings", json=attempt("s1")))
    assert_429(await client.post("/bookings", json=attempt("s1", name="")))
    available = {s["id"]: s["available"] for s in (await client.get("/slots")).json()["slots"]}
    assert available["s1"] is True


async def test_attempts_without_a_usable_email_are_not_counted(client: AsyncClient, slots):
    # Nothing to count them against; each is a 400 for the missing email.
    for email in (None, "", "   ", 42):
        for _ in range(3):
            body = {"slot_id": "s1", "name": "Ada"} | ({} if email is None else {"email": email})
            assert (await client.post("/bookings", json=body)).status_code == 400


async def test_simultaneous_attempts_still_let_only_five_through(client: AsyncClient, slots):
    gate = asyncio.Event()

    async def send():
        await gate.wait()
        return await client.post("/bookings", json=attempt())

    tasks = [asyncio.create_task(send()) for _ in range(12)]
    await asyncio.sleep(0)
    gate.set()
    responses = await asyncio.gather(*tasks)

    statuses = Counter(r.status_code for r in responses)
    assert statuses == {404: 5, 429: 7}, statuses


async def test_the_window_slides(client: AsyncClient, slots, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(ratelimit_constants, "WINDOW_SECONDS", 1)
    for _ in range(5):
        await client.post("/bookings", json=attempt())
    assert_429(await client.post("/bookings", json=attempt()))

    await asyncio.sleep(1.1)

    assert (await client.post("/bookings", json=attempt("s1"))).status_code == 201


async def test_idempotent_replays_are_not_counted_and_not_blocked(client: AsyncClient, slots):
    key = {"Idempotency-Key": "k-1"}
    first = await client.post("/bookings", json=attempt("s1"), headers=key)  # attempt 1
    for _ in range(10):
        replay = await client.post("/bookings", json=attempt("s1"), headers=key)
        assert replay.status_code == 201
    for i in range(2, 6):  # attempts 2-5
        await client.post("/bookings", json=attempt(f"s{i}"))
    assert_429(await client.post("/bookings", json=attempt("s6")))  # attempt 6

    # Over the limit, a replay still returns the stored response rather than a 429.
    replay = await client.post("/bookings", json=attempt("s1"), headers=key)
    assert replay.status_code == 201
    assert replay.content == first.content


async def test_a_429_is_not_stored_as_the_idempotent_response(client: AsyncClient, slots):
    for _ in range(5):
        await client.post("/bookings", json=attempt())

    assert_429(
        await client.post("/bookings", json=attempt("s1"), headers={"Idempotency-Key": "k-2"})
    )

    async with engine.connect() as conn:
        stored = await conn.execute(
            text("SELECT count(*) FROM idempotency_keys WHERE key = 'k-2'")
        )
        assert stored.scalar_one() == 0


async def test_reset_clears_the_limits(client: AsyncClient, slots):
    for _ in range(6):
        await client.post("/bookings", json=attempt())

    await client.post("/reset", json={"slots": SLOTS})

    assert (await client.post("/bookings", json=attempt("s1"))).status_code == 201


async def test_redis_down_fails_open(
    client: AsyncClient, slots, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    from redis.asyncio import Redis

    from src.ratelimit import service as ratelimit_service

    dead = Redis.from_url("redis://localhost:1/0", socket_connect_timeout=0.2, socket_timeout=0.2)
    monkeypatch.setattr(ratelimit_service, "redis_client", dead)

    with caplog.at_level(logging.WARNING, logger="src.ratelimit.service"):
        statuses = [(await client.post("/bookings", json=attempt())).status_code for _ in range(7)]
        booked = await client.post("/bookings", json=attempt("s1"))

    assert statuses == [404] * 7
    assert booked.status_code == 201
    assert any("rate limit skipped" in r.getMessage() for r in caplog.records)
