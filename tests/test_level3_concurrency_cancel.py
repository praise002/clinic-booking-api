"""Level 3: two people can never book the same slot, even at the exact same moment (task-1.md)."""

import asyncio
from collections import Counter

from httpx import AsyncClient
import pytest
from sqlalchemy import text

from src.database import engine

SLOT = {
    "id": "s1",
    "provider": "Dr Ade",
    "start": "2030-01-01T09:00:00Z",
    "end": "2030-01-01T09:30:00Z",
}
RACERS = 50


@pytest.fixture
async def slot(client: AsyncClient) -> None:
    response = await client.post("/reset", json={"slots": [SLOT]})
    assert response.status_code == 200, response.text


async def confirmed_rows(slot_id: str) -> int:
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT count(*) FROM bookings WHERE slot_id = :slot AND status = 'confirmed'"),
            {"slot": slot_id},
        )
        return result.scalar_one()


async def test_booking_a_booked_slot_is_409(client: AsyncClient, slot):
    first = await client.post(
        "/bookings", json={"slot_id": "s1", "name": "Ada Obi", "email": "ada@example.com"}
    )
    second = await client.post(
        "/bookings", json={"slot_id": "s1", "name": "Bola Ade", "email": "bola@example.com"}
    )

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json() == {"error": "slot already booked"}
    assert await confirmed_rows("s1") == 1


async def test_fifty_simultaneous_bookings_give_one_201_and_49_409s(client: AsyncClient, slot):
    # Every request waits on the same gate, then all go at once. Different emails, so
    # only the slot is contended (the Level 5 rate limit is per email).
    gate = asyncio.Event()

    async def book(n: int):
        await gate.wait()
        return await client.post(
            "/bookings",
            json={"slot_id": "s1", "name": f"Patient {n}", "email": f"patient{n}@example.com"},
        )

    tasks = [asyncio.create_task(book(n)) for n in range(RACERS)]
    await asyncio.sleep(0)
    gate.set()
    responses = await asyncio.gather(*tasks)

    statuses = Counter(r.status_code for r in responses)
    assert statuses == {201: 1, 409: RACERS - 1}, statuses
    assert all(
        r.json() == {"error": "slot already booked"} for r in responses if r.status_code == 409
    )
    assert await confirmed_rows("s1") == 1

    winner = next(r.json() for r in responses if r.status_code == 201)
    stored = await client.get(f"/bookings/{winner['id']}")
    assert stored.json()["status"] == "confirmed"
    slots = (await client.get("/slots")).json()["slots"]
    assert slots[0]["available"] is False


# ── Cancel ───────────────────────────────────────────────────────────────────


async def book(client: AsyncClient, email: str = "ada@example.com") -> dict:
    response = await client.post(
        "/bookings", json={"slot_id": "s1", "name": "Ada Obi", "email": email}
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_cancelling_returns_200_with_the_cancelled_booking(client: AsyncClient, slot):
    booking = await book(client)

    response = await client.delete(f"/bookings/{booking['id']}")

    assert response.status_code == 200
    assert response.json() == {**booking, "status": "cancelled"}
    stored = await client.get(f"/bookings/{booking['id']}")
    assert stored.json()["status"] == "cancelled"


async def test_cancelling_twice_is_409(client: AsyncClient, slot):
    booking = await book(client)
    await client.delete(f"/bookings/{booking['id']}")

    response = await client.delete(f"/bookings/{booking['id']}")

    assert response.status_code == 409
    assert response.json() == {"error": "booking already cancelled"}


@pytest.mark.parametrize("booking_id", ["00000000-0000-4000-8000-000000000000", "not-a-uuid"])
async def test_cancelling_an_unknown_booking_is_404(client: AsyncClient, slot, booking_id):
    response = await client.delete(f"/bookings/{booking_id}")

    assert response.status_code == 404
    assert response.json() == {"error": "booking not found"}


async def test_a_cancelled_slot_can_be_booked_again(client: AsyncClient, slot):
    first = await book(client)
    await client.delete(f"/bookings/{first['id']}")

    slots = (await client.get("/slots")).json()["slots"]
    assert slots[0]["available"] is True

    second = await client.post(
        "/bookings", json={"slot_id": "s1", "name": "Bola Ade", "email": "bola@example.com"}
    )
    assert second.status_code == 201, second.text
    assert second.json()["id"] != first["id"]
    # The old booking stays, cancelled; only the new one is confirmed.
    assert (await client.get(f"/bookings/{first['id']}")).json()["status"] == "cancelled"
    assert await confirmed_rows("s1") == 1
    assert (await client.get("/slots")).json()["slots"][0]["available"] is False


async def test_two_simultaneous_cancels_give_one_200_and_one_409(client: AsyncClient, slot):
    booking = await book(client)
    gate = asyncio.Event()

    async def cancel():
        await gate.wait()
        return await client.delete(f"/bookings/{booking['id']}")

    tasks = [asyncio.create_task(cancel()) for _ in range(2)]
    await asyncio.sleep(0)
    gate.set()
    responses = await asyncio.gather(*tasks)

    assert sorted(r.status_code for r in responses) == [200, 409]


async def test_after_a_cancel_fifty_simultaneous_rebookings_still_give_one_winner(
    client: AsyncClient, slot
):
    booking = await book(client)
    await client.delete(f"/bookings/{booking['id']}")
    gate = asyncio.Event()

    async def rebook(n: int):
        await gate.wait()
        return await client.post(
            "/bookings",
            json={"slot_id": "s1", "name": f"Patient {n}", "email": f"patient{n}@example.com"},
        )

    tasks = [asyncio.create_task(rebook(n)) for n in range(RACERS)]
    await asyncio.sleep(0)
    gate.set()
    responses = await asyncio.gather(*tasks)

    assert Counter(r.status_code for r in responses) == {201: 1, 409: RACERS - 1}
    assert await confirmed_rows("s1") == 1
