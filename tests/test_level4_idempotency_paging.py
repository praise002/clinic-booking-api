"""Level 4: a retried request never creates a duplicate booking (task-1.md)."""

import asyncio
import json

from httpx import AsyncClient
import pytest
from sqlalchemy import text

from src.database import engine
from tests.conftest import API_KEY

SLOTS = [
    {
        "id": "s1",
        "provider": "Dr Ade",
        "start": "2030-01-01T09:00:00Z",
        "end": "2030-01-01T09:30:00Z",
    },
    {
        "id": "s2",
        "provider": "Dr Ade",
        "start": "2030-01-02T09:00:00Z",
        "end": "2030-01-02T09:30:00Z",
    },
    {
        "id": "past",
        "provider": "Dr Ade",
        "start": "2020-01-01T09:00:00Z",
        "end": "2020-01-01T09:30:00Z",
    },
]
BOOKING = {"slot_id": "s1", "name": "Ada Obi", "email": "ada@example.com"}
MISMATCH = {"error": "Idempotency-Key reused with a different body"}


@pytest.fixture
async def slots(client: AsyncClient) -> None:
    response = await client.post("/reset", json={"slots": SLOTS})
    assert response.status_code == 200, response.text


async def booking_rows() -> int:
    async with engine.connect() as conn:
        return (await conn.execute(text("SELECT count(*) FROM bookings"))).scalar_one()


def keyed(key: str) -> dict:
    return {"Idempotency-Key": key}


# ── Idempotency ──────────────────────────────────────────────────────────────


async def test_a_retry_with_the_same_key_and_body_replays_the_same_booking(
    client: AsyncClient, slots
):
    first = await client.post("/bookings", json=BOOKING, headers=keyed("k-1"))
    retry = await client.post("/bookings", json=BOOKING, headers=keyed("k-1"))

    assert first.status_code == retry.status_code == 201
    assert retry.json() == first.json()
    assert await booking_rows() == 1


async def test_the_same_json_written_differently_is_the_same_body(client: AsyncClient, slots):
    first = await client.post("/bookings", json=BOOKING, headers=keyed("k-1"))
    reordered = json.dumps(
        {"email": "ada@example.com", "name": "Ada Obi", "slot_id": "s1"}, indent=2
    )
    retry = await client.post(
        "/bookings",
        content=reordered,
        headers={**keyed("k-1"), "Content-Type": "application/json"},
    )

    assert retry.status_code == 201
    assert retry.json()["id"] == first.json()["id"]
    assert await booking_rows() == 1


async def test_the_same_key_with_a_different_body_is_422(client: AsyncClient, slots):
    await client.post("/bookings", json=BOOKING, headers=keyed("k-1"))

    response = await client.post(
        "/bookings", json={**BOOKING, "slot_id": "s2"}, headers=keyed("k-1")
    )

    assert response.status_code == 422
    assert response.json() == MISMATCH
    assert await booking_rows() == 1
    slots_now = {s["id"]: s["available"] for s in (await client.get("/slots")).json()["slots"]}
    assert slots_now["s2"] is True


@pytest.mark.parametrize(
    ("body", "status"),
    [
        ({**BOOKING, "email": "not-an-email"}, 400),
        ({**BOOKING, "slot_id": "past"}, 400),
        ({**BOOKING, "slot_id": "nope"}, 404),
    ],
)
async def test_a_failed_attempt_is_replayed_too(client: AsyncClient, slots, body, status):
    first = await client.post("/bookings", json=body, headers=keyed("k-1"))
    retry = await client.post("/bookings", json=body, headers=keyed("k-1"))

    assert first.status_code == retry.status_code == status
    assert retry.json() == first.json()


async def test_a_409_is_replayed_even_after_the_slot_frees_up(client: AsyncClient, slots):
    taken = (await client.post("/bookings", json={**BOOKING, "email": "bola@example.com"})).json()
    first = await client.post("/bookings", json=BOOKING, headers=keyed("k-1"))
    await client.delete(f"/bookings/{taken['id']}")

    retry = await client.post("/bookings", json=BOOKING, headers=keyed("k-1"))

    # The retry gets the same response as the first attempt, not a new attempt.
    assert first.status_code == retry.status_code == 409
    assert retry.json() == {"error": "slot already booked"}
    assert (await client.post("/bookings", json=BOOKING, headers=keyed("k-2"))).status_code == 201


async def test_simultaneous_retries_with_one_key_create_one_booking(client: AsyncClient, slots):
    gate = asyncio.Event()

    async def send():
        await gate.wait()
        return await client.post("/bookings", json=BOOKING, headers=keyed("k-race"))

    tasks = [asyncio.create_task(send()) for _ in range(10)]
    await asyncio.sleep(0)
    gate.set()
    responses = await asyncio.gather(*tasks)

    assert [r.status_code for r in responses] == [201] * 10
    assert len({r.json()["id"] for r in responses}) == 1
    assert await booking_rows() == 1


async def test_different_keys_are_different_requests(client: AsyncClient, slots):
    first = await client.post("/bookings", json=BOOKING, headers=keyed("k-1"))
    second = await client.post("/bookings", json=BOOKING, headers=keyed("k-2"))

    assert first.status_code == 201
    assert second.status_code == 409


async def test_without_a_key_nothing_is_replayed(client: AsyncClient, slots):
    first = await client.post("/bookings", json=BOOKING)
    second = await client.post("/bookings", json=BOOKING)

    assert (first.status_code, second.status_code) == (201, 409)


async def test_an_empty_key_counts_as_no_key(client: AsyncClient, slots):
    first = await client.post("/bookings", json=BOOKING, headers=keyed(""))
    second = await client.post("/bookings", json=BOOKING, headers=keyed(""))

    assert (first.status_code, second.status_code) == (201, 409)


async def test_a_key_longer_than_255_characters_is_400(client: AsyncClient, slots):
    response = await client.post("/bookings", json=BOOKING, headers=keyed("k" * 256))

    assert response.status_code == 400
    assert response.json() == {"error": "Idempotency-Key must be at most 255 characters"}
    assert await booking_rows() == 0


async def test_a_rejected_api_key_does_not_use_up_the_idempotency_key(
    client: AsyncClient, anon_client: AsyncClient, slots
):
    rejected = await anon_client.post(
        "/bookings", json=BOOKING, headers={**keyed("k-1"), "X-API-Key": API_KEY + "x"}
    )
    accepted = await client.post("/bookings", json=BOOKING, headers=keyed("k-1"))

    assert rejected.status_code == 401
    assert accepted.status_code == 201


async def test_a_malformed_body_does_not_use_up_the_key(client: AsyncClient, slots):
    bad = await client.post(
        "/bookings",
        content=b"{not json",
        headers={**keyed("k-1"), "Content-Type": "application/json"},
    )
    good = await client.post("/bookings", json=BOOKING, headers=keyed("k-1"))

    assert bad.status_code == 400
    assert good.status_code == 201


async def test_reset_forgets_idempotency_keys(client: AsyncClient, slots):
    first = await client.post("/bookings", json=BOOKING, headers=keyed("k-1"))
    await client.post("/reset", json={"slots": SLOTS})

    after = await client.post("/bookings", json=BOOKING, headers=keyed("k-1"))

    assert after.status_code == 201
    assert after.json()["id"] != first.json()["id"]
