# Verification Report

**Scope:** level-5 (the whole contract, Koya Levels 1–5: reset, slots, book, look up; API key and validation; no double booking, cancel; idempotent retries, paging; per-email rate limit; plus the web page for all of it)
**Target:** local — API http://localhost:8070 (Docker Compose: 2 gunicorn workers, Postgres, Redis), page http://localhost:5180 (Vite dev server + `api/_proxy.js`). No deployed URL yet (slice 9).
**Date:** 2026-10-26
**Blockers:** 0
**Major:** 1
**Minor:** 2
**Verdict:** PASS
**Not verified:** deployed URL (slice 9: re-run `scripts/smoke.py` and `scripts/concurrency.py` against Railway, and the browser journeys against Vercel).

## Findings

| # | Severity | Level | Location | Finding | Why it matters | Remediation |
|---|---|---|---|---|---|---|
| 1 | major (carried, accepted) | 2 | `src/core/auth.py` `PUBLIC_PATHS` | `/health` and the docs answer without a key; `task-1.md` says every request needs one. Recorded learner decision. | A checker probing those exact paths without a key gets 200, not 401. | None unless the decision changes. |
| 2 | minor | 5 | `src/ratelimit/service.py` (`ratelimit:<email>` keys) | The rate limit counts by the raw email string, of any length, before validation: a 200,000-character "email" was stored as a 200,022-byte Redis key (probe AC). Keys expire after 60 s. | Someone could fill Redis memory for a minute with huge junk emails, and the request body has no size cap. It's a hardening gap, not a contract one. | Key the counter on a SHA-256 of the normalised email (fixed 64 characters), and/or reject bodies over a small size. Valid emails are at most 254 characters. |
| 3 | minor | 1 | FastAPI default `redirect_slashes` (`src/main.py`) | A trailing slash (`/bookings/`, `/slots/`, `/health/`, also `POST /bookings/`) gets `307 Temporary Redirect` to the slash-less path, with no `{"error"}` body, and the `Location` is `http://…`. | Outside the contract's paths, but every other unknown path is `404 {"error"}`. Behind Railway's HTTPS proxy, a client following the redirect would be sent to `http://`. | `FastAPI(redirect_slashes=False)` so trailing-slash paths are plain `404 {"error": "not found"}`, plus a test. |

**Notes (not findings):**
- **Rate limit and the other levels:** with Level 5 on, one email gets at most 5 booking attempts a minute. A checker that ran Level 3's "many requests at the same moment" check **from one email** would see 5 answers and then 429s rather than 409s. The contract asks for both rules, so its own checks presumably use different emails, as `scripts/concurrency.py` does; `/reset` also clears the counts. Nothing to change; worth knowing.
- Rejected (429) attempts aren't recorded, so a client that keeps retrying gets in once the oldest attempt is 60 s old (probe AB: allowed again at 61 s).
- A probe in the first run looked like a 6th attempt getting 201; that probe's 5th attempt used `lim@example` (no `.com`), a different email. The redo (probe X) shows the 6th attempt for one email is 429.

## Requirement map

| # | Level | Requirement (from task-1.md) | Test that proves it | Live check | Status |
|---|---|---|---|---|---|
| 1–9 | 1 | reset, slots, book, get, error shape, persistence | `test_level1_slots_bookings.py` (13) | smoke 1–12; restart of api **and** redis → booking still there | verified |
| 10–22 | 2 | key 401s, validation 400s, 404 slot, 400 started, trim/lower | `test_level2_auth_validation.py` (61) | smoke 13–26; probe Z (401 before 429) | verified |
| 23–30 | 3 | 409, 409 under concurrency, cancel 200/404/409, slot freed | `test_level3_concurrency_cancel.py` (9) | smoke 27–32; `concurrency.py` race 1 PASS | verified |
| 31–43 | 4 | idempotent replay (same status, id, bytes), 422, one booking under concurrent retries; paging oldest first, case-insensitive, no gaps/dupes, `next_cursor` null at the end, limit 1–50 | `test_level4_idempotency_paging.py` (38) | smoke 33–41; `concurrency.py` race 2 PASS (20×201, 1 body, 1 booking) | verified |
| 44 | 5 | At most 5 attempts per email per minute; the 6th → 429 | `test_the_sixth_attempt_in_a_minute_is_429` (asserts body + `Retry-After`) | smoke; probe X (6th → 429) | verified |
| 45 | 5 | Failed attempts included | `test_failed_attempts_count` (404, 400, 201, 409, 404 → 429) | probe X (404, 400, 201, 409, 400 → 429) | verified |
| 46 | 5 | `Retry-After` in whole seconds | every 429 test asserts digits only, 1–60 | probes X/AA (`60`, then `55` after 5 s) | verified |
| 47 | 5 | Other emails aren't affected | `test_other_emails_are_not_affected` | smoke; probe Y | verified |
| 48 | 5 (spec) | Per normalised email (trim + lower case) | `test_the_limit_is_per_email_after_trim_and_lower_case` | probe X (mixed case and spaces) | verified |
| 49 | 5 (spec) | Holds under simultaneous attempts, across workers | `test_simultaneous_attempts_still_let_only_five_through` (10/10 runs in slice 8) | probe AE: 15 parallel curl → 5×404, 10×429 | verified |
| 50 | 5 (spec) | Sliding window | `test_the_window_slides` (1 s window) | probe AB: allowed again 61 s after the first attempt | verified |
| 51 | 5 (spec) | Replays not counted, never refused; 429 not stored for a key | `test_idempotent_replays_are_not_counted_and_not_blocked`, `test_a_429_is_not_stored_as_the_idempotent_response` | probe AD | verified |
| 52 | 5 (spec) | `/reset` clears the limits; checked before validation | `test_reset_clears_the_limits`, `test_a_429_is_checked_before_validation_and_creates_nothing` | smoke "POST /reset clears the rate limit" | verified |
| 53 | 5 (spec) | Redis down → fail open, quickly | `test_redis_down_fails_open` | slice 8: Redis stopped → bookings proceed + warning; Redis paused → 0.51 s per booking | verified |
| 54 | 5 (PRD) | Page: 429 says how many seconds to wait | — | browser `ratelimit` journey: "Please wait 59 seconds"; another email books at once | verified |
| 55 | all (PRD) | Page journeys (book, errors, cancel, My Bookings, admin) | `npm test` (proxy, incl. `Retry-After` passthrough) | all 6 browser journeys re-run (below) | verified |

**Test reality check:** every Level 5 test asserts the status, the `{"error": "too many booking attempts, try again later"}` body and a digits-only `Retry-After` in 1–60. Tests outside Level 5 lift the limit through a fixture; the 12 Level 5 tests (marked `real_rate_limit`) and `smoke.py` run with the real limit.

## Security pass (OWASP, all levels)

- **A01:** every endpoint and unknown route is 401 without the key; the key is checked before the rate limit (probe Z), so unauthenticated traffic can't even consume a victim's attempts.
- **A02:** API key 0 hits in either repo's history; only `.env.example` tracked.
- **A03:** no string-built SQL; the Redis key and Lua arguments are passed as `KEYS`/`ARGV`, never spliced into the script.
- **A04:** double booking (partial unique index), double cancel (conditional `UPDATE`), duplicate retries (key claimed in the booking's transaction) and spam (atomic Lua) are each enforced by the data store, not by read-then-write in Python. Rate-limit key size is unbounded (finding 2).
- **A05:** errors never leak stack traces; trailing-slash redirects (finding 3).
- **A06:** `pip-audit` and `npm audit` clean.
- **A09:** 0 email addresses in the API logs. 401s are logged (method, path, client); Redis outages are logged as warnings.

## Commands run

```
$ make tests
collected 138 items
============================= 138 passed in 15.47s =============================
$ uv run ruff check && uv run ruff format --check
All checks passed!
51 files already formatted
$ uv run alembic check
No new upgrade operations detected.
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
OK    same Idempotency-Key + body: same status and booking id
OK    same Idempotency-Key, different body: 422
OK    POST /reset deletes every booking
OK    GET /bookings pages: oldest first, each once, ends with next_cursor null
OK    GET /bookings limit=0: 400
OK    GET /bookings limit=51: 400
OK    GET /bookings limit=abc: 400
OK    GET /bookings without email: 400
OK    GET /bookings with a bad cursor: 400
OK    5 failed attempts for one email are all answered (404)
OK    the 6th attempt is 429 with a whole-seconds Retry-After
OK    another email in the same minute is unaffected
OK    POST /reset clears the rate limit

All checks passed
$ BASE_URL=http://localhost:8070 uv run python scripts/concurrency.py
50 simultaneous bookings for one slot against http://localhost:8070
  finished in 0.64s
  201: 1
  409: 49
  winner: 525eaacd-9f40-4fd8-a761-b2f85e8ff3ed (Racer 0), status confirmed
  slot 'race' available: False
PASS: exactly one booking won

20 simultaneous retries with one Idempotency-Key
  201: 20
  distinct response bodies: 1
  bookings for retry.racer@example.com: 1
PASS: one booking, every retry got the same response
$ (frontend) npm test
ℹ pass 5
ℹ fail 0
```

Level 5 HTTP probes (`curl -i`, local API; `post` = `POST /bookings` with the key):

```
### X (redo). 5 attempts for one email: 404, 400, 201, 409, 400 (non-string slot_id), then the 6th
HTTP/1.1 404 Not Found {"error":"slot not found"} 
HTTP/1.1 400 Bad Request {"error":"name is required"} 
HTTP/1.1 201 Created {"id":"44fa1d2c-27d2-4d03-802a-f3bfa93b1804","slot_id":"x1","name":"A","email":"lim@example.com","status":"confirmed","created_at":"2026-10-26T03:23:29.360Z"} 
HTTP/1.1 409 Conflict {"error":"slot already booked"} 
HTTP/1.1 400 Bad Request {"error":"slot_id must be a string"} 
HTTP/1.1 429 Too Many Requests retry-after: 60 {"error":"too many booking attempts, try again later"} 
### Y (redo). another email, same moment, free slot
HTTP/1.1 201 Created {"id":"c1bbbf73-22fe-42da-830c-03dbd4ed7a4e","slot_id":"x2","name":"B","email":"other@example.com","status":"confirmed","created_at":"2026-10-26T03:23:29.536Z"} 
### Z. wrong API key from the limited email: 401 comes first
{"error":"invalid or missing API key"} [401]
### AA. Retry-After counts down
HTTP/1.1 429 Too Many Requests retry-after: 55 {"error":"too many booking attempts, try again later"} 
### AB. after the window slides (waiting until 61s after the first attempt)
HTTP/1.1 404 Not Found {"error":"slot not found"} 
HTTP/1.1 404 Not Found {"error":"slot not found"} 
### AC. very long email string as the rate-limit key
{"error":"email is not valid"} [400]
   key length: 200022
### AD. keyed booking over the limit: the replay still answers, a new key is refused
HTTP/1.1 201 Created {"id":"22de3c65-77dc-476a-8ca5-6f7c36f0
HTTP/1.1 201 Created {"id":"22de3c65-77dc-476a-8ca5-6f7c36f0
HTTP/1.1 429 Too Many Requests retry-after: 60 {"error":"too many booking attempts, try again later"} 
### AE. 15 parallel curl processes, one email
      5 404
     10 429
```

(Z, AA, AB and AC are from the first probe run, whose X/Y used a mistyped email, explained in the notes above; AA is that email's real 6th attempt.)

Trailing slashes and persistence:

```
--- GET /bookings/
HTTP/1.1 307 Temporary Redirect
location: http://localhost:8070/bookings
--- GET /slots/
HTTP/1.1 307 Temporary Redirect
location: http://localhost:8070/slots
--- GET /health/
HTTP/1.1 307 Temporary Redirect
location: http://localhost:8070/health
--- GET /bookings/?email=a@b.io
HTTP/1.1 307 Temporary Redirect
location: http://localhost:8070/bookings?email=a@b.io
--- POST /bookings/
HTTP/1.1 307 Temporary Redirect
location: http://localhost:8070/bookings
### persistence: book, restart api + redis, fetch
{"id":"62b8f23d-cd63-4a60-840f-1b61a658d2cb","slot_id":"keep","name":"Keep","email":"keep@example.com","status":"confirmed","created_at":"2026-10-26T03:25:13.107Z"} [200]
```

Browser regression (headless Chromium via http://localhost:5180), security:

```
### browser: journey
  'Failed to load resource: the server responded with a status of 404 (Not Found)',
  'Failed to load resource: the server responded with a status of 401 (Unauthorized)'
]
### browser: level2
PAST slot row     -> Dr Bola | Wed 1 Jan 2020, 10:00–10:30 | Unavailable
slot started      -> This slot has already started. Please pick another.
row after refresh -> Dr Soon | Mon 26 Oct 2026, 04:24–04:53 | Unavailable
### browser: level3
page message: Someone just booked this slot. Please pick another.
row after refresh: Unavailable
### browser: cancel
   other tab DELETE: 200
  dialog: "Are you sure you want to cancel this booking?" -> OK
   message: This booking is already cancelled. | status shown: cancelled
### browser: mybookings
phone width horizontal scroll: false
nobody@example.com -> No bookings for this email.
blank email -> Please enter your email.
### browser: ratelimit
attempt 5: That email doesn't look right. Please check it and try again.
attempt 6: Too many booking attempts for this email. Please wait 59 seconds and try again.
another email straight away: booked 58ebf1ff-59a0-4e7b-9d67-9f26c91d50bc
### secrets
.: key hits=0; tracked env: .env.example 
../clinic-booking-frontend: key hits=0; tracked env: .env.example 
### string-built SQL
none
### emails in API logs
0
### pip-audit
No known vulnerabilities found
### npm audit
found 0 vulnerabilities
```

(The journey's two console errors are deliberate: the unknown-id lookup (404) and the reset with a wrong key (401). Its earlier lines (booking, find, filter, phone width) passed, shown in full in the slice 8 regression.)
