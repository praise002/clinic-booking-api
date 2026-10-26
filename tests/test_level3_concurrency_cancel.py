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
