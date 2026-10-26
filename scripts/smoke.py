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

    # Each check books as its own email: the Level 5 limit allows 5 attempts per email a minute.
    for name, body, message in [
        (
            "missing slot_id",
            {"name": "Ada Obi", "email": "check1@example.com"},
            "slot_id is required",
        ),
        (
            "missing name",
            {"slot_id": "smoke-2", "email": "check2@example.com"},
            "name is required",
        ),
        (
            "empty name",
            {**good_booking, "name": "", "email": "check3@example.com"},
            "name is required",
        ),
        ("missing email", {"slot_id": "smoke-2", "name": "Ada Obi"}, "email is required"),
        ("empty email", {**good_booking, "email": "   "}, "email is required"),
        ("invalid email", {**good_booking, "email": "not-an-email"}, "email is not valid"),
        (
            "non-string slot_id",
            {**good_booking, "slot_id": 2, "email": "check4@example.com"},
            "slot_id must be a string",
        ),
        (
            "slot already started",
            {**good_booking, "slot_id": "smoke-past", "email": "check5@example.com"},
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
        json={"slot_id": "smoke-2", "name": "  Ada Obi  ", "email": "  Trim.Check@Example.COM "},
    )
    trimmed = r.json() if r.status_code == 201 else {}
    check(
        "name trimmed, email trimmed and lower-cased",
        (trimmed.get("name"), trimmed.get("email")) == ("Ada Obi", "trim.check@example.com"),
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

    # ── Level 4: idempotent retries ─────────────────────────────────────────
    key = {"Idempotency-Key": f"smoke-{datetime.now(UTC).timestamp()}"}
    retry_body = {"slot_id": "smoke-2", "name": "Retry Test", "email": "retry@example.com"}
    client.delete(f"/bookings/{trimmed.get('id')}")  # free smoke-2 (booked by the trim check)
    first = client.post("/bookings", json=retry_body, headers=key)
    again = client.post("/bookings", json=retry_body, headers=key)
    check(
        "same Idempotency-Key + body: same status and booking id",
        first.status_code == again.status_code == 201 and first.json() == again.json(),
        f"{first.text} / {again.text}",
    )
    r = client.post("/bookings", json={**retry_body, "name": "Someone Else"}, headers=key)
    check(
        "same Idempotency-Key, different body: 422",
        is_error(r, 422, "Idempotency-Key reused with a different body"),
        r.text,
    )

    # ── Reset wipes bookings (last: it empties the target) ───────────────────
    r = client.post("/reset", json={"slots": slots})
    r = client.get(f"/bookings/{booking.get('id')}")
    check("POST /reset deletes every booking", is_error(r, 404), r.text)

    # ── Level 4: paging through a person's bookings ─────────────────────────
    page_slots = [
        {
            "id": f"smoke-page-{i}",
            "provider": "Dr Ade",
            "start": iso(start + timedelta(days=1, hours=i)),
            "end": iso(start + timedelta(days=1, hours=i, minutes=30)),
        }
        for i in range(5)
    ]
    client.post("/reset", json={"slots": page_slots})
    made = [
        client.post(
            "/bookings",
            json={"slot_id": s["id"], "name": "Pager", "email": "Pager@Example.com"},
        ).json()["id"]
        for s in page_slots
    ]
    seen, sizes, cursor = [], [], None
    for _ in range(10):
        params = {"email": "  PAGER@example.COM ", "limit": 2}
        if cursor:
            params["cursor"] = cursor
        page = client.get("/bookings", params=params).json()
        sizes.append(len(page.get("bookings", [])))
        seen += [b["id"] for b in page.get("bookings", [])]
        cursor = page.get("next_cursor")
        if cursor is None:
            break
    check(
        "GET /bookings pages: oldest first, each once, ends with next_cursor null",
        seen == made and sizes == [2, 2, 1] and cursor is None,
        f"sizes {sizes}",
    )
    for limit in ("0", "51", "abc"):
        r = client.get("/bookings", params={"email": "pager@example.com", "limit": limit})
        check(f"GET /bookings limit={limit}: 400", is_error(r, 400), r.text)
    r = client.get("/bookings")
    check("GET /bookings without email: 400", is_error(r, 400), r.text)
    r = client.get("/bookings", params={"email": "pager@example.com", "cursor": "nonsense"})
    check("GET /bookings with a bad cursor: 400", is_error(r, 400), r.text)

    # ── Level 5: rate limit (the paging section's reset cleared earlier counts) ──
    spammer = {"slot_id": "missing-slot", "name": "Spam", "email": "spammer@example.com"}
    statuses = [client.post("/bookings", json=spammer).status_code for _ in range(5)]
    check(
        "5 failed attempts for one email are all answered (404)", statuses == [404] * 5, statuses
    )
    r = client.post("/bookings", json={**spammer, "email": "  SPAMMER@example.com "})
    retry_after = r.headers.get("Retry-After", "")
    check(
        "the 6th attempt is 429 with a whole-seconds Retry-After",
        is_error(r, 429, "too many booking attempts, try again later")
        and retry_after.isdigit()
        and 1 <= int(retry_after) <= 60,
        f"{r.status_code} Retry-After={retry_after!r} {r.text}",
    )
    r = client.post("/bookings", json={**spammer, "email": "not.a.spammer@example.com"})
    check("another email in the same minute is unaffected", is_error(r, 404), r.text)
    client.post("/reset", json={"slots": page_slots})
    r = client.post("/bookings", json={**spammer, "slot_id": "smoke-page-0"})
    check("POST /reset clears the rate limit", r.status_code == 201, r.text)

    print(f"\n{'All checks passed' if not failures else f'{failures} check(s) failed'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
