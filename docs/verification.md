# Verification Report

**Scope:** level-3 (Koya Levels 1–3: reset, slots, book, look up; API key and booking validation; no double booking under simultaneous requests; cancel; plus the web page for all three)
**Target:** local — API http://localhost:8070 (Docker Compose, 2 gunicorn workers, Postgres), page http://localhost:5180 (Vite dev server + `api/_proxy.js`). No deployed URL yet (deployment is slice 9).
**Date:** 2026-10-26
**Blockers:** 0
**Major:** 1
**Minor:** 0
**Verdict:** PASS
**Not verified:** deployed URL (doesn't exist yet, slice 9; `scripts/concurrency.py` and `scripts/smoke.py` must be re-run against it there).

## Findings

| # | Severity | Level | Location | Finding | Why it matters | Remediation |
|---|---|---|---|---|---|---|
| 1 | major (carried from level-2, accepted) | 2 | `src/core/auth.py` `PUBLIC_PATHS`; `spec.md > Decisions and Open Issues` | `GET /health`, `/docs`, `/redoc` and `/openapi.json` answer without a key, while `task-1.md` says every request needs one. Both are recorded learner decisions; counted as major only because the skill treats any spec/contract disagreement as major. | A checker probing exactly those paths without a key would get 200 instead of 401. Every contract endpoint and unknown route is 401 without the key. | None unless the decision changes. |

No new findings at Level 3.

**Notes (not findings):**
- The contract's example body for `DELETE /bookings/{id}` 200 shows `"status": "confirmed"`, but its description says "Sets status to cancelled". The API follows the description and returns `"status": "cancelled"`. It's clearly a copy of the booking example, so this is the right reading.
- A slot that is both booked and started gets `400 slot has already started` (probe M): the started check runs before the insert. The contract doesn't order the two.
- In probe L, a cancel raced against 20 rebookings: one rebooking won after the cancel committed, and the rest got 409. Zero winners would also have been correct, if every rebooking had reached the index before the cancel committed. The invariant (at most one confirmed booking) held.

## Requirement map

| # | Level | Requirement (from task-1.md) | Test that proves it | Live check | Status |
|---|---|---|---|---|---|
| 1–9 | 1 | reset (200, wipes bookings, keeps past slots), slots (earliest first, `available`, provider exact), book 201, get 200/404, `{"error"}` shape, persistence | `test_level1_slots_bookings.py` (13 tests), reverified by the suite | smoke lines 1–12; restart probe O | verified |
| 10–22 | 2 | key 401 (missing/wrong/before validation), 400s (missing/empty/non-string/invalid email/bad body), 404 unknown slot, 400 started, trim + lower-case, rejected booking creates nothing | `test_level2_auth_validation.py` (60 cases), reverified by the suite | smoke lines 13–26; probe N (DELETE without key 401) | verified |
| 23 | 3 | A slot that already has a confirmed booking → 409 | `test_booking_a_booked_slot_is_409` (asserts `{"error": "slot already booked"}` and 1 confirmed row) | smoke "booking an already-booked slot is 409" | verified |
| 24 | 3 | **409 holds when many requests arrive at the same moment** | `test_fifty_simultaneous_bookings_give_one_201_and_49_409s` (asyncio.gather, 1×201 / 49×409, 409 bodies, 1 confirmed row in Postgres) | `scripts/concurrency.py` PASS; probe H (30 separate curl processes → 1×201, 29×409, 1 row); probe I (two slots at once → one winner each) | verified |
| 25 | 3 | `DELETE /bookings/{id}` → 200 with the booking, status `cancelled` | `test_cancelling_returns_200_with_the_cancelled_booking` (body equals the booking with status cancelled; GET agrees) | smoke; probe K | verified |
| 26 | 3 | Cancel frees the slot | `test_a_cancelled_slot_can_be_booked_again` (available true, rebook 201, old stays cancelled, 1 confirmed row) | smoke "available again" + "booked again"; probe O after restart | verified |
| 27 | 3 | Unknown booking → 404 `{"error"}` | `test_cancelling_an_unknown_booking_is_404[uuid, not-a-uuid]` | smoke | verified |
| 28 | 3 | Already cancelled → 409 `{"error"}` | `test_cancelling_twice_is_409` | smoke; probe J | verified |
| 29 | 3 (spec) | Two simultaneous cancels → one 200, one 409 | `test_two_simultaneous_cancels_give_one_200_and_one_409` | probe J (10 parallel → 1×200, 9×409) | verified |
| 30 | 3 (spec) | After a cancel, simultaneous rebookings still give one winner | `test_after_a_cancel_fifty_simultaneous_rebookings_still_give_one_winner` | probe L | verified |
| 31 | 3 (PRD) | Page: 409 message + slot refresh; cancel with "are you sure?" (no → nothing changes); row and confirmation show cancelled; slot freed; "already cancelled" message | — | headless Chromium runs (below) | verified |

**Test reality check:** each Level 3 test asserts the status code **and** the body (`{"error": "<exact message>"}` or the full booking), and the race tests also count rows directly in Postgres. In slice 4, the 50-way test failed with the index dropped (`Counter({201: 50})`), so it can detect double booking. The three race tests passed 10/10 consecutive runs in slices 4–5.

## Security pass (OWASP, Levels 1–3)

- **A01:** `DELETE` without a key is 401 (probe N); every endpoint is covered by the middleware.
- **A02:** 0 hits for the API key in either repo's history; only `.env.example` tracked. The 3 database-URL matches are documentation mentioning the `postgresql://` scheme, with no credentials.
- **A03:** no string-built SQL. The cancel is a parameterized SQLAlchemy `update()`.
- **A04 (insecure design, the core of this level):** no check-then-insert anywhere. Double booking is prevented by the partial unique index `uq_bookings_slot_confirmed`, and double cancel by a single conditional `UPDATE … WHERE status = 'confirmed'`. Both are enforced by Postgres, under 2 worker processes.
- **A06:** `pip-audit` and `npm audit` clean.
- **A09:** 401s logged without key, query or body (fixed after level-2).

## Commands run

```
$ make tests
collected 88 items
============================== 88 passed in 5.56s ==============================
$ uv run ruff check && uv run ruff format --check
All checks passed!
36 files already formatted
$ make smoke
BASE_URL=${BASE_URL:-http://localhost:8070} uv run python scripts/smoke.py
Smoke test against http://localhost:8070

OK    GET /health is 200, with no key
OK    POST /reset is 200 {status: ok}
OK    GET /slots is 200, earliest first, past slots kept
OK    GET /slots marks free slots available
OK    GET /slots?provider= is an exact match
OK    POST /bookings is 201 confirmed
OK    booking created_at has milliseconds and Z
OK    GET /bookings/{id} returns the same booking
OK    the booked slot is now unavailable
OK    GET unknown booking is 404 {error}
OK    POST /bookings for an unknown slot is 404 {error}
OK    unknown route is 404 {error}
OK    no API key is 401 {error}
OK    wrong API key is 401 {error}
OK    unknown route without a key is 401
OK    API docs load without a key
OK    POST /bookings, missing slot_id: 400
OK    POST /bookings, missing name: 400
OK    POST /bookings, empty name: 400
OK    POST /bookings, missing email: 400
OK    POST /bookings, empty email: 400
OK    POST /bookings, invalid email: 400
OK    POST /bookings, non-string slot_id: 400
OK    POST /bookings, slot already started: 400
OK    POST /bookings, malformed JSON: 400
OK    name trimmed, email trimmed and lower-cased
OK    booking an already-booked slot is 409
OK    DELETE /bookings/{id} is 200 cancelled
OK    cancelling again is 409
OK    cancelling an unknown booking is 404
OK    the cancelled booking's slot is available again
OK    the freed slot can be booked again
OK    POST /reset deletes every booking

All checks passed
$ BASE_URL=http://localhost:8070 uv run python scripts/concurrency.py
50 simultaneous bookings for one slot against http://localhost:8070
  finished in 0.74s
  201: 1
  409: 49
  winner: 0ab1f391-7a43-47ca-ac5b-4e7f16274ce3 (Racer 0), status confirmed
  slot 'race' available: False
PASS: exactly one booking won
$ (frontend) npm test
ℹ pass 5
ℹ fail 0
```

Independent HTTP probes (separate `curl` processes via `xargs -P`, local API):

```
### H. 30 separate curl processes in parallel, same slot
      1 201
     29 409
confirmed rows for a: 1
### I. two slots raced at once (20 each, interleaved)
      1 a 201
     19 a 409
      1 b 201
     19 b 409
### J. 10 parallel cancels of one booking
      1 200 "status":"cancelled"
      9 409 already cancelled
### K. DELETE response body vs GET after
HTTP/1.1 200 OK
{"id":"7d4bad05-7bf4-4f1a-89f4-2fe71918ff7c","slot_id":"a","name":"Ada","email":"ada@example.com","status":"cancelled","created_at":"2026-10-26T02:38:30.122Z"}
### L. cancel and 20 rebooks fired together (booking already exists)
      1 book 201
     19 book 409
      1 cancel 200
cancelled: 1
confirmed: 1
### M. booked AND started slot (which error wins?)
{"error":"slot has already started"} [400]
### N. DELETE without key / wrong method on /bookings/{id}
{"error":"invalid or missing API key"} [401]
{"error":"method not allowed"} [405]
### O. cancelled status persists across restart
{'past': False, 'a': True, 'b': True}
```

(O: `a` is available again after its booking was cancelled and the API restarted; `past` is unavailable because probe M inserted a confirmed booking for it directly in Postgres.)

Web page (headless Chromium via http://localhost:5180), security:

```
### web page: 409 (someone books first)
someone else booked it first: 201
page still shows it as: Selected
page message: Someone just booked this slot. Please pick another.
row after refresh: Unavailable
### web page: cancel journey
booked 4210b99f-9d40-4f99-8c41-0394e8b37543 | slot row: Unavailable
1. press Cancel booking, answer no:
  dialog: "Are you sure you want to cancel this booking?" -> Cancel
   status: confirmed | slot row: Unavailable
2. press Cancel booking, answer yes:
  dialog: "Are you sure you want to cancel this booking?" -> OK
   status: cancelled | cancel button still there: false | slot row: Choose
   Book a Slot confirmation now says: This booking has been cancelled. The slot is free again. | status: cancelled
3. rebook the freed slot:
   booked again: 4cd288a1-4818-453b-b7cb-f0945dfacb06 | slot row: Unavailable
4. cancelled in another tab, then cancel here:
   other tab DELETE: 200
  dialog: "Are you sure you want to cancel this booking?" -> OK
   message: This booking is already cancelled. | status shown: cancelled
### secrets
.: key hits=0; tracked env: .env.example 
../clinic-booking-frontend: key hits=0; tracked env: .env.example 
db URLs with real passwords committed: 3   (all three are docs mentioning the postgresql:// scheme; no credentials)
### raw SQL with string building
none
### pip-audit
No known vulnerabilities found
### npm audit
found 0 vulnerabilities
```
