"""Level 4: a retried request never creates a duplicate booking, and a person can page through
their bookings (task-1.md)."""

import asyncio
from datetime import UTC, datetime, timedelta
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


async def test_a_replay_is_byte_for_byte_the_first_response(client: AsyncClient, slots):
    # Not just equal JSON: the same text, key order included, for 201s and errors alike.
    for body in (BOOKING, {**BOOKING, "slot_id": "nope"}):
        key = keyed(f"bytes-{body['slot_id']}")
        first = await client.post("/bookings", json=body, headers=key)
        retry = await client.post("/bookings", json=body, headers=key)

        assert retry.status_code == first.status_code
        assert retry.content == first.content
        assert retry.headers["content-type"] == first.headers["content-type"]


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


# ── Paging through a person's bookings ───────────────────────────────────────


def many_slots(n: int) -> list[dict]:
    first = datetime(2030, 2, 1, 9, tzinfo=UTC)
    return [
        {
            "id": f"p{i:02}",
            "provider": "Dr Ade",
            "start": (first + timedelta(hours=i)).isoformat(),
            "end": (first + timedelta(hours=i, minutes=30)).isoformat(),
        }
        for i in range(n)
    ]


async def book_many(client: AsyncClient, n: int, email: str = "ada@example.com") -> list[str]:
    """n bookings for one email, interleaved with someone else's; returns ids, oldest first."""
    await client.post("/reset", json={"slots": many_slots(2 * n)})
    ids = []
    for i in range(n):
        mine = await client.post(
            "/bookings", json={"slot_id": f"p{2 * i:02}", "name": "Ada", "email": email}
        )
        assert mine.status_code == 201, mine.text
        ids.append(mine.json()["id"])
        other = await client.post(
            "/bookings",
            json={"slot_id": f"p{2 * i + 1:02}", "name": "Bo", "email": "bo@example.com"},
        )
        assert other.status_code == 201
    return ids


async def walk(client: AsyncClient, email: str, limit: int | None = None) -> list[list[dict]]:
    pages, cursor = [], None
    while True:
        params = {"email": email}
        if limit is not None:
            params["limit"] = limit
        if cursor is not None:
            params["cursor"] = cursor
        response = await client.get("/bookings", params=params)
        assert response.status_code == 200, response.text
        body = response.json()
        assert set(body) == {"bookings", "next_cursor"}
        pages.append(body["bookings"])
        cursor = body["next_cursor"]
        if cursor is None:
            return pages
        assert len(pages) < 50, "paging never ended"


async def test_pages_walk_every_booking_once_oldest_first(client: AsyncClient):
    ids = await book_many(client, 25)

    pages = await walk(client, "ada@example.com", limit=10)

    assert [len(p) for p in pages] == [10, 10, 5]
    assert [b["id"] for page in pages for b in page] == ids
    assert all(b["email"] == "ada@example.com" for page in pages for b in page)


async def test_the_default_page_size_is_10(client: AsyncClient):
    await book_many(client, 12)

    body = (await client.get("/bookings", params={"email": "ada@example.com"})).json()

    assert len(body["bookings"]) == 10
    assert body["next_cursor"] is not None


async def test_an_exact_multiple_ends_without_an_empty_page(client: AsyncClient):
    await book_many(client, 20)

    pages = await walk(client, "ada@example.com", limit=10)

    assert [len(p) for p in pages] == [10, 10]


async def test_the_email_match_ignores_case_and_spaces(client: AsyncClient):
    ids = await book_many(client, 3)

    pages = await walk(client, "  ADA@Example.COM ")

    assert [b["id"] for b in pages[0]] == ids


async def test_cancelled_bookings_are_included(client: AsyncClient):
    ids = await book_many(client, 3)
    await client.delete(f"/bookings/{ids[1]}")

    bookings = (await walk(client, "ada@example.com"))[0]

    assert [(b["id"], b["status"]) for b in bookings] == [
        (ids[0], "confirmed"),
        (ids[1], "cancelled"),
        (ids[2], "confirmed"),
    ]


async def test_an_email_with_no_bookings_gets_an_empty_last_page(client: AsyncClient, slots):
    response = await client.get("/bookings", params={"email": "nobody@example.com"})

    assert response.status_code == 200
    assert response.json() == {"bookings": [], "next_cursor": None}


async def test_bookings_made_at_the_same_instant_still_page_without_gaps(client: AsyncClient):
    # created_at ties are broken by id, so a page boundary between them loses nothing.
    await client.post("/reset", json={"slots": many_slots(7)})
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO bookings (id, slot_id, name, email, status, created_at) "
                "SELECT gen_random_uuid(), id, 'Ada', 'ada@example.com', 'confirmed', "
                "'2026-10-01T12:00:00Z' FROM slots"
            )
        )
        expected = [
            str(row[0])
            for row in await conn.execute(text("SELECT id FROM bookings ORDER BY created_at, id"))
        ]

    pages = await walk(client, "ada@example.com", limit=3)

    assert [len(p) for p in pages] == [3, 3, 1]
    assert [b["id"] for page in pages for b in page] == expected


@pytest.mark.parametrize("limit", ["1", "50"])
async def test_limit_accepts_1_to_50(client: AsyncClient, slots, limit: str):
    response = await client.get("/bookings", params={"email": "ada@example.com", "limit": limit})

    assert response.status_code == 200


@pytest.mark.parametrize("limit", ["0", "51", "-1", "abc", "1.5", ""])
async def test_any_other_limit_is_400(client: AsyncClient, slots, limit: str):
    response = await client.get("/bookings", params={"email": "ada@example.com", "limit": limit})

    assert response.status_code == 400
    assert response.json() == {"error": "limit must be an integer from 1 to 50"}


@pytest.mark.parametrize("params", [{}, {"email": ""}, {"email": "   "}])
async def test_the_email_is_required(client: AsyncClient, slots, params: dict):
    response = await client.get("/bookings", params=params)

    assert response.status_code == 400
    assert response.json() == {"error": "email is required"}


@pytest.mark.parametrize(
    "cursor",
    [
        "garbage!",
        "bm90IGEgY3Vyc29y",  # base64 of "not a cursor"
        "MjAyNi0xMC0wMVQxMjowMDowMHxub3QtYS11dWlk",  # "2026-10-01T12:00:00|not-a-uuid"
        "",
    ],
)
async def test_a_bad_cursor_is_400(client: AsyncClient, slots, cursor: str):
    response = await client.get("/bookings", params={"email": "ada@example.com", "cursor": cursor})

    assert response.status_code == 400
    assert response.json() == {"error": "cursor is not valid"}
