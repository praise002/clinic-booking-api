"""End-to-end contract walk against a running API.

    BASE_URL=http://localhost:8070 API_KEY=... uv run python scripts/smoke.py

It calls /reset, so it wipes every booking on the target. Prints one OK/FAIL line per
check and exits non-zero if any check failed.
"""

from datetime import UTC, datetime, timedelta
import os
import re
import sys

import httpx

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8070").rstrip("/")
API_KEY = os.environ.get("API_KEY", "")

failures = 0


def check(name: str, condition: bool, detail: object = "") -> None:
    global failures
    if condition:
        print(f"OK    {name}")
    else:
        failures += 1
        print(f"FAIL  {name}  {detail}")


def is_error(response: httpx.Response, status: int, message: str | None = None) -> bool:
    """The contract's error shape: the status, and a body of exactly {"error": <message>}."""
    try:
        body = response.json()
    except ValueError:
        return False
    if response.status_code != status or not isinstance(body, dict) or set(body) != {"error"}:
        return False
    return message is None or body["error"] == message


def iso(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> int:
    client = httpx.Client(base_url=BASE_URL, headers={"X-API-Key": API_KEY}, timeout=15)
    anon = httpx.Client(base_url=BASE_URL, timeout=15)
    start = (datetime.now(UTC) + timedelta(days=30)).replace(
        hour=9, minute=0, second=0, microsecond=0
    )
    slots = [
        {
            # Slots in the past are kept by /reset, and can't be booked (Level 2).
            "id": "smoke-past",
            "provider": "Dr Bola",
            "start": "2020-01-01T09:00:00Z",
            "end": "2020-01-01T09:30:00Z",
        },
        {
            "id": "smoke-2",
            "provider": "Dr Bola",
            "start": iso(start + timedelta(hours=1)),
            "end": iso(start + timedelta(hours=1, minutes=30)),
        },
        {
            "id": "smoke-1",
            "provider": "Dr Ade",
            "start": iso(start),
            "end": iso(start + timedelta(minutes=30)),
        },
    ]
    print(f"Smoke test against {BASE_URL}\n")

    # ── Level 1 ──────────────────────────────────────────────────────────────
    r = anon.get("/health")
    check("GET /health is 200, with no key", r.status_code == 200, r.text)

    r = client.post("/reset", json={"slots": slots})
    check(
        "POST /reset is 200 {status: ok}",
        r.status_code == 200 and r.json() == {"status": "ok"},
        r.text,
    )

    r = client.get("/slots")
    listed = r.json().get("slots", []) if r.status_code == 200 else []
    check(
        "GET /slots is 200, earliest first, past slots kept",
        [s["id"] for s in listed] == ["smoke-past", "smoke-1", "smoke-2"],
        r.text,
    )
    check(
        "GET /slots marks free slots available",
        all(s["available"] is True for s in listed),
        listed,
    )

    r = client.get("/slots", params={"provider": "Dr Ade"})
    check(
        "GET /slots?provider= is an exact match",
        [s["id"] for s in r.json().get("slots", [])] == ["smoke-1"],
        r.text,
    )

    good_booking = {"slot_id": "smoke-1", "name": "Ada Obi", "email": "ada@example.com"}
    r = client.post("/bookings", json=good_booking)
    booking = r.json()
    check(
        "POST /bookings is 201 confirmed",
        r.status_code == 201 and booking.get("status") == "confirmed",
        r.text,
    )
    check(
        "booking created_at has milliseconds and Z",
        bool(
            re.match(
                r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$", booking.get("created_at", "")
            )
        ),
        booking,
    )

    r = client.get(f"/bookings/{booking.get('id')}")
    check(
        "GET /bookings/{id} returns the same booking",
        r.status_code == 200 and r.json() == booking,
        r.text,
    )

    r = client.get("/slots")
    available = {s["id"]: s["available"] for s in r.json().get("slots", [])}
    check(
        "the booked slot is now unavailable",
        available == {"smoke-past": True, "smoke-1": False, "smoke-2": True},
        available,
    )

    r = client.get("/bookings/00000000-0000-4000-8000-000000000000")
    check(
        "GET unknown booking is 404 {error}",
        is_error(r, 404),
        r.text,
    )

    r = client.post(
        "/bookings", json={"slot_id": "missing", "name": "Ada Obi", "email": "ada@example.com"}
    )
    check(
        "POST /bookings for an unknown slot is 404 {error}",
        is_error(r, 404),
        r.text,
    )

    r = client.get("/nowhere")
    check("unknown route is 404 {error}", is_error(r, 404), r.text)

    # ── Level 2 ──────────────────────────────────────────────────────────────
    r = anon.get("/slots")
    check("no API key is 401 {error}", is_error(r, 401), r.text)

    r = anon.post("/bookings", json=good_booking, headers={"X-API-Key": "wrong"})
    check("wrong API key is 401 {error}", is_error(r, 401), r.text)

    r = anon.get("/nowhere")
    check("unknown route without a key is 401", is_error(r, 401), r.text)

    r = anon.get("/docs")
    check("API docs load without a key", r.status_code == 200, r.status_code)

    for name, body, message in [
        (
            "missing slot_id",
            {"name": "Ada Obi", "email": "ada@example.com"},
            "slot_id is required",
        ),
        ("missing name", {"slot_id": "smoke-2", "email": "ada@example.com"}, "name is required"),
        ("empty name", {**good_booking, "name": ""}, "name is required"),
        ("missing email", {"slot_id": "smoke-2", "name": "Ada Obi"}, "email is required"),
        ("empty email", {**good_booking, "email": "   "}, "email is required"),
        ("invalid email", {**good_booking, "email": "not-an-email"}, "email is not valid"),
        ("non-string slot_id", {**good_booking, "slot_id": 2}, "slot_id must be a string"),
        (
            "slot already started",
            {**good_booking, "slot_id": "smoke-past"},
            "slot has already started",
        ),
    ]:
        r = client.post("/bookings", json=body)
        check(f"POST /bookings, {name}: 400", is_error(r, 400, message), r.text)

    r = client.post(
        "/bookings", content=b"{not json", headers={"Content-Type": "application/json"}
    )
    check("POST /bookings, malformed JSON: 400", is_error(r, 400), r.text)

    r = client.post(
        "/bookings",
        json={"slot_id": "smoke-2", "name": "  Ada Obi  ", "email": "  Ada@Example.COM "},
    )
    trimmed = r.json() if r.status_code == 201 else {}
    check(
        "name trimmed, email trimmed and lower-cased",
        (trimmed.get("name"), trimmed.get("email")) == ("Ada Obi", "ada@example.com"),
        r.text,
    )

    # ── Level 3 ──────────────────────────────────────────────────────────────
    # (The simultaneous-bookings proof is scripts/concurrency.py.)
    r = client.post("/bookings", json={**good_booking, "email": "someone.else@example.com"})
    check("booking an already-booked slot is 409", is_error(r, 409, "slot already booked"), r.text)

    r = client.delete(f"/bookings/{booking.get('id')}")
    check(
        "DELETE /bookings/{id} is 200 cancelled",
        r.status_code == 200 and r.json() == {**booking, "status": "cancelled"},
        r.text,
    )
    r = client.delete(f"/bookings/{booking.get('id')}")
    check("cancelling again is 409", is_error(r, 409, "booking already cancelled"), r.text)

    r = client.delete("/bookings/00000000-0000-4000-8000-000000000000")
    check("cancelling an unknown booking is 404", is_error(r, 404), r.text)

    r = client.get("/slots")
    freed = {s["id"]: s["available"] for s in r.json().get("slots", [])}.get("smoke-1")
    check("the cancelled booking's slot is available again", freed is True, r.text)

    r = client.post("/bookings", json={**good_booking, "email": "rebook@example.com"})
    check("the freed slot can be booked again", r.status_code == 201, r.text)

    # ── Reset wipes bookings (last: it empties the target) ───────────────────
    r = client.post("/reset", json={"slots": slots})
    r = client.get(f"/bookings/{booking.get('id')}")
    check("POST /reset deletes every booking", is_error(r, 404), r.text)

    print(f"\n{'All checks passed' if not failures else f'{failures} check(s) failed'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
