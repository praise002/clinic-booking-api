"""Level 1: reset, list slots, book a slot, look up a booking (task-1.md)."""

import re
import uuid

from httpx import AsyncClient
import pytest

CREATED_AT = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")

SLOTS = [
    # Sent out of order, to prove the list is sorted by start.
    {
        "id": "s2",
        "provider": "Dr Bola",
        "start": "2030-01-01T10:00:00Z",
        "end": "2030-01-01T10:30:00Z",
    },
    {
        "id": "s1",
        "provider": "Dr Ade",
        "start": "2030-01-01T09:00:00Z",
        "end": "2030-01-01T09:30:00Z",
    },
    {
        "id": "s3",
        "provider": "Dr Ade",
        "start": "2030-01-02T09:00:00Z",
        "end": "2030-01-02T09:30:00Z",
    },
]
BOOKING = {"slot_id": "s1", "name": "Ada Obi", "email": "ada@example.com"}


async def reset(client: AsyncClient, slots=SLOTS) -> None:
    response = await client.post("/reset", json={"slots": slots})
    assert response.status_code == 200, response.text


async def test_reset_returns_ok(client: AsyncClient):
    response = await client.post("/reset", json={"slots": SLOTS})

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_slots_are_listed_earliest_first_with_availability(client: AsyncClient):
    await reset(client)

    response = await client.get("/slots")

    assert response.status_code == 200
    assert response.json() == {
        "slots": [
            {
                "id": "s1",
                "provider": "Dr Ade",
                "start": "2030-01-01T09:00:00Z",
                "end": "2030-01-01T09:30:00Z",
                "available": True,
            },
            {
                "id": "s2",
                "provider": "Dr Bola",
                "start": "2030-01-01T10:00:00Z",
                "end": "2030-01-01T10:30:00Z",
                "available": True,
            },
            {
                "id": "s3",
                "provider": "Dr Ade",
                "start": "2030-01-02T09:00:00Z",
                "end": "2030-01-02T09:30:00Z",
                "available": True,
            },
        ]
    }


async def test_slot_times_with_an_offset_come_back_in_utc(client: AsyncClient):
    await reset(
        client,
        [
            {
                "id": "s1",
                "provider": "Dr Ade",
                "start": "2030-01-01T10:00:00+01:00",
                "end": "2030-01-01T10:30:00+01:00",
            }
        ],
    )

    slot = (await client.get("/slots")).json()["slots"][0]

    assert slot["start"] == "2030-01-01T09:00:00Z"
    assert slot["end"] == "2030-01-01T09:30:00Z"


async def test_provider_filter_is_an_exact_match(client: AsyncClient):
    await reset(client)

    ade = (await client.get("/slots", params={"provider": "Dr Ade"})).json()["slots"]
    lower = (await client.get("/slots", params={"provider": "dr ade"})).json()["slots"]

    assert [s["id"] for s in ade] == ["s1", "s3"]
    assert lower == []


async def test_reset_keeps_past_slots_and_replaces_everything(client: AsyncClient):
    await reset(client)
    await client.post("/bookings", json=BOOKING)
    past = {
        "id": "old",
        "provider": "Dr Ade",
        "start": "2020-01-01T09:00:00Z",
        "end": "2020-01-01T09:30:00Z",
    }

    await reset(client, [past])

    slots = (await client.get("/slots")).json()["slots"]
    assert [s["id"] for s in slots] == ["old"]


async def test_reset_deletes_every_booking(client: AsyncClient):
    await reset(client)
    booking_id = (await client.post("/bookings", json=BOOKING)).json()["id"]

    await reset(client)

    assert (await client.get(f"/bookings/{booking_id}")).status_code == 404
    assert all(s["available"] for s in (await client.get("/slots")).json()["slots"])


async def test_reset_with_a_bad_body_is_400_in_the_error_shape(client: AsyncClient):
    await reset(client)

    missing = await client.post("/reset", json={"slots": [{"id": "s1", "provider": "Dr Ade"}]})
    duplicate = await client.post("/reset", json={"slots": [SLOTS[0], SLOTS[0]]})

    for response in (missing, duplicate):
        assert response.status_code == 400
        assert set(response.json()) == {"error"}
    # A rejected reset changes nothing.
    assert len((await client.get("/slots")).json()["slots"]) == 3


async def test_booking_a_slot_returns_201_confirmed(client: AsyncClient):
    await reset(client)

    response = await client.post("/bookings", json=BOOKING)

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"id", "slot_id", "name", "email", "status", "created_at"}
    uuid.UUID(body["id"])
    assert body["slot_id"] == "s1"
    assert body["name"] == "Ada Obi"
    assert body["email"] == "ada@example.com"
    assert body["status"] == "confirmed"
    assert CREATED_AT.match(body["created_at"]), body["created_at"]


async def test_a_booked_slot_is_listed_as_unavailable(client: AsyncClient):
    await reset(client)
    await client.post("/bookings", json=BOOKING)

    slots = {s["id"]: s["available"] for s in (await client.get("/slots")).json()["slots"]}

    assert slots == {"s1": False, "s2": True, "s3": True}


async def test_booking_an_unknown_slot_is_404(client: AsyncClient):
    await reset(client)

    response = await client.post("/bookings", json={**BOOKING, "slot_id": "nope"})

    assert response.status_code == 404
    assert response.json() == {"error": "slot not found"}


async def test_a_booking_can_be_looked_up_by_id(client: AsyncClient):
    await reset(client)
    created = (await client.post("/bookings", json=BOOKING)).json()

    response = await client.get(f"/bookings/{created['id']}")

    assert response.status_code == 200
    assert response.json() == created


async def test_an_unknown_booking_id_is_404(client: AsyncClient):
    unknown = await client.get(f"/bookings/{uuid.uuid4()}")
    not_a_uuid = await client.get("/bookings/not-a-uuid")

    for response in (unknown, not_a_uuid):
        assert response.status_code == 404
        assert response.json() == {"error": "booking not found"}


async def test_unknown_routes_and_methods_keep_the_error_shape(client: AsyncClient):
    unknown = await client.get("/nowhere")
    wrong_method = await client.put("/slots")

    assert unknown.status_code == 404
    assert set(unknown.json()) == {"error"}
    assert wrong_method.status_code == 405
    assert set(wrong_method.json()) == {"error"}


async def test_health(client: AsyncClient):
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize(
    ("method", "path"),
    [("GET", "/bookings/"), ("GET", "/slots/"), ("POST", "/bookings/"), ("GET", "/health/")],
)
async def test_a_trailing_slash_is_a_404_not_a_redirect(client: AsyncClient, method, path):
    response = await client.request(method, path, json={})

    assert response.status_code == 404
    assert response.json() == {"error": "not found"}


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("postgres://u:p@h:5432/db", "postgresql+asyncpg://u:p@h:5432/db"),
        ("postgresql://u:p@h:5432/db", "postgresql+asyncpg://u:p@h:5432/db"),
        ("postgresql+asyncpg://u:p@h:5432/db", "postgresql+asyncpg://u:p@h:5432/db"),
    ],
)
def test_host_database_urls_get_the_asyncpg_driver(given: str, expected: str):
    from src.config import use_asyncpg

    assert use_asyncpg(given) == expected
