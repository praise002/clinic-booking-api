"""Two races against a running API: no double booking (Level 3), no duplicate retry (Level 4).

    BASE_URL=http://localhost:8070 API_KEY=... uv run python scripts/concurrency.py [N]

1. N simultaneous bookings for one slot, each from a different email (so only the slot is
   contended, not the Level 5 per-email rate limit): exactly 1×201 and (N-1)×409.
2. 20 simultaneous retries of one booking with the same Idempotency-Key and body: all get
   the same status and booking id, byte for byte, and the person has exactly one booking.

It calls /reset, so it wipes every booking on the target. Exits non-zero if either fails.
"""

import asyncio
from collections import Counter
from datetime import UTC, datetime, timedelta
import os
import sys
import time

import httpx

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8070").rstrip("/")
API_KEY = os.environ.get("API_KEY", "")
RACERS = int(sys.argv[1]) if len(sys.argv) > 1 else 50
RETRIES = 20


async def main() -> int:
    start = datetime.now(UTC) + timedelta(days=30)
    slot = {
        "id": "race",
        "provider": "Dr Ade",
        "start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "end": (start + timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    retry_slot = {**slot, "id": "retry-race"}
    limits = httpx.Limits(max_connections=RACERS, max_keepalive_connections=RACERS)
    async with httpx.AsyncClient(
        base_url=BASE_URL, headers={"X-API-Key": API_KEY}, timeout=60, limits=limits
    ) as client:
        r = await client.post("/reset", json={"slots": [slot, retry_slot]})
        if r.status_code != 200:
            print(f"reset failed: {r.status_code} {r.text}")
            return 1

        # Open every connection first, so the bookings themselves leave together.
        await asyncio.gather(*(client.get("/health") for _ in range(RACERS)))
        gate = asyncio.Event()

        async def book(n: int) -> httpx.Response:
            await gate.wait()
            return await client.post(
                "/bookings",
                json={"slot_id": "race", "name": f"Racer {n}", "email": f"racer{n}@example.com"},
            )

        tasks = [asyncio.create_task(book(n)) for n in range(RACERS)]
        await asyncio.sleep(0.1)
        began = time.perf_counter()
        gate.set()
        responses = await asyncio.gather(*tasks)
        elapsed = time.perf_counter() - began

        statuses = Counter(r.status_code for r in responses)
        winners = [r.json() for r in responses if r.status_code == 201]
        print(f"{RACERS} simultaneous bookings for one slot against {BASE_URL}")
        print(f"  finished in {elapsed:.2f}s")
        for status, count in sorted(statuses.items()):
            print(f"  {status}: {count}")

        ok = statuses == {201: 1, 409: RACERS - 1}
        bodies_ok = all(
            r.json() == {"error": "slot already booked"} for r in responses if r.status_code == 409
        )
        if winners:
            stored = (await client.get(f"/bookings/{winners[0]['id']}")).json()
            slots = {s["id"]: s for s in (await client.get("/slots")).json()["slots"]}
            print(f"  winner: {stored['id']} ({stored['name']}), status {stored['status']}")
            print(f"  slot 'race' available: {slots['race']['available']}")
            ok = ok and stored["status"] == "confirmed" and slots["race"]["available"] is False
        ok = ok and bodies_ok
        print("PASS: exactly one booking won" if ok else "FAIL: double booking race")

        # ── Race 2: simultaneous retries with one Idempotency-Key ──────────────
        key = f"retry-race-{time.time_ns()}"
        body = {"slot_id": "retry-race", "name": "Retry Racer", "email": "retry.racer@example.com"}
        gate = asyncio.Event()

        async def retry() -> httpx.Response:
            await gate.wait()
            return await client.post("/bookings", json=body, headers={"Idempotency-Key": key})

        tasks = [asyncio.create_task(retry()) for _ in range(RETRIES)]
        await asyncio.sleep(0.1)
        gate.set()
        retries = await asyncio.gather(*tasks)

        statuses = Counter(r.status_code for r in retries)
        bodies = {r.content for r in retries}
        listed = (await client.get("/bookings", params={"email": body["email"]})).json()
        print(f"\n{RETRIES} simultaneous retries with one Idempotency-Key")
        for status, count in sorted(statuses.items()):
            print(f"  {status}: {count}")
        print(f"  distinct response bodies: {len(bodies)}")
        print(f"  bookings for {body['email']}: {len(listed['bookings'])}")
        retry_ok = statuses == {201: RETRIES} and len(bodies) == 1 and len(listed["bookings"]) == 1
        print(
            "PASS: one booking, every retry got the same response"
            if retry_ok
            else "FAIL: retry race"
        )

    return 0 if ok and retry_ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
