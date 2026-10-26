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


def iso(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> int:
    client = httpx.Client(base_url=BASE_URL, headers={"X-API-Key": API_KEY}, timeout=15)
    start = (datetime.now(UTC) + timedelta(days=30)).replace(
        hour=9, minute=0, second=0, microsecond=0
    )
    slots = [
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
    r = client.get("/health")
    check("GET /health is 200", r.status_code == 200, r.text)

    r = client.post("/reset", json={"slots": slots})
    check(
        "POST /reset is 200 {status: ok}",
        r.status_code == 200 and r.json() == {"status": "ok"},
        r.text,
    )

    r = client.get("/slots")
    listed = r.json().get("slots", []) if r.status_code == 200 else []
    check(
        "GET /slots is 200, earliest first",
        [s["id"] for s in listed] == ["smoke-1", "smoke-2"],
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

    r = client.post(
        "/bookings", json={"slot_id": "smoke-1", "name": "Ada Obi", "email": "ada@example.com"}
    )
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
        available == {"smoke-1": False, "smoke-2": True},
        available,
    )

    r = client.get("/bookings/00000000-0000-4000-8000-000000000000")
    check(
        "GET unknown booking is 404 {error}",
        r.status_code == 404 and set(r.json()) == {"error"},
        r.text,
    )

    r = client.post(
        "/bookings", json={"slot_id": "missing", "name": "Ada Obi", "email": "ada@example.com"}
    )
    check(
        "POST /bookings for an unknown slot is 404 {error}",
        r.status_code == 404 and set(r.json()) == {"error"},
        r.text,
    )

    print(f"\n{'All checks passed' if not failures else f'{failures} check(s) failed'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
