# Verification Report

**Scope:** level-4 (Koya Levels 1–4: reset, slots, book, look up; API key and validation; no double booking, cancel; idempotent retries; a person's bookings with cursor paging; plus the web page for all of it)
**Target:** local — API http://localhost:8070 (Docker Compose, 2 gunicorn workers, Postgres), page http://localhost:5180 (Vite dev server + `api/_proxy.js`). No deployed URL yet (slice 9).
**Date:** 2026-10-26
**Blockers:** 0
**Major:** 3
**Minor:** 0
**Verdict:** PASS
**Not verified:** deployed URL (slice 9).

## Findings

| # | Severity | Level | Location | Finding | Why it matters | Remediation |
|---|---|---|---|---|---|---|
| 1 | major | 4 | `idempotency_keys.response` is `JSONB` (migration 0001, `src/idempotency/models.py`) | A replayed response has the same status and the same values as the first, but **its keys come back in a different order**: first `{"id","slot_id","name","email","status","created_at"}`, replay `{"id","name","email","status","slot_id","created_at"}` (probes P, P2). `JSONB` stores objects in its own key order. | The contract says "the same response". A checker that parses JSON sees identical bodies; one that compares the raw text of the two responses would see them differ. | **Fixed:** migration `0002` makes `response` a `json` column (keeps the text as written), the model matches (`alembic check` clean), `test_a_replay_is_byte_for_byte_the_first_response` failed before and passes after, and `spec.md > Data Model` is updated. |
| 2 | major | 4 | `scripts/concurrency.py`, `scripts/smoke.py` | No live script sends **simultaneous** retries with one `Idempotency-Key`. It's covered by `test_simultaneous_retries_with_one_key_create_one_booking` and probe R, but nothing will prove it against the deployed URL in slice 9. Counted major per the skill's rule for level-3+ behaviours. | The deployed API (2 workers, Railway Postgres) would have its idempotency race proven only by the local test, not live. | **Fixed:** `scripts/concurrency.py` now also fires 20 simultaneous retries with one key: 3 local runs gave 20×201, 1 distinct response body (byte-identical), 1 booking in `GET /bookings?email=`. |
| 3 | major (carried, accepted) | 2 | `src/core/auth.py` `PUBLIC_PATHS` | `/health` and the docs answer without a key; `task-1.md` says every request needs one. Recorded learner decision. | A checker probing those exact paths without a key gets 200, not 401. | None unless the decision changes. |

**Notes (not findings):**
- **Replay after a cancel** (probe S): a retry with the key of a booking that has since been cancelled gets the original `201` body with `"status": "confirmed"`, while `GET /bookings/{id}` says `cancelled`. That is what "the same key returns the same response" means. The replay is the record of what the first request got, not a fresh read.
- `limit=05` is accepted as 5. It's digits from 1 to 50; the contract only rules out values outside 1–50 and non-integers.
- A cursor is a position, not tied to an email; a well-formed cursor past every booking returns an empty last page (`next_cursor: null`) rather than a 400 (probe V). Only cursors the API couldn't have made are 400.

## Requirement map

| # | Level | Requirement (from task-1.md) | Test that proves it | Live check | Status |
|---|---|---|---|---|---|
| 1–9 | 1 | reset, slots, book, get, error shape, persistence | `test_level1_slots_bookings.py` (13) | smoke 1–12 | verified |
| 10–22 | 2 | 401s, validation 400s, 404 slot, 400 started, trim/lower | `test_level2_auth_validation.py` (61) | smoke 13–26; probe W (no key → 401) | verified |
| 23–30 | 3 | 409 booked, 409 under concurrency, cancel 200/404/409, slot freed | `test_level3_concurrency_cancel.py` (9) | smoke 27–32; `scripts/concurrency.py` PASS | verified |
| 31 | 4 | Same key + same body → same status code | `test_a_retry_with_the_same_key_and_body_replays_the_same_booking`, `test_a_failed_attempt_is_replayed_too[400/400/404]`, `test_a_409_is_replayed_even_after_the_slot_frees_up` | smoke; probe P | verified |
| 32 | 4 | … same booking id | same tests (`retry.json() == first.json()`) | smoke; probes P, R (1 distinct id) | verified (body bytes differ in key order: finding 1) |
| 33 | 4 | … never creates a second booking | `booking_rows() == 1` in the replay tests; `test_simultaneous_retries_with_one_key_create_one_booking` (10 at once) | probe P/R: 1 booking in `GET /bookings?email=`; 20 parallel curl → 20×201, 1 id | verified (no live script for slice 9: finding 2) |
| 34 | 4 | Same key + different body → 422 | `test_the_same_key_with_a_different_body_is_422` (asserts `{"error": ...}` and that no booking was made) | smoke; probe Q | verified |
| 35 | 4 (spec) | Same JSON written differently is the same body | `test_the_same_json_written_differently_is_the_same_body` | — | verified |
| 36 | 4 (spec) | 401 / malformed body don't use up the key; reset forgets keys; key > 255 → 400; blank key = no key | `test_a_rejected_api_key_does_not_use_up_the_idempotency_key`, `test_a_malformed_body_does_not_use_up_the_key`, `test_reset_forgets_idempotency_keys`, `test_a_key_longer_than_255_characters_is_400`, `test_an_empty_key_counts_as_no_key` | — | verified |
| 37 | 4 | `GET /bookings`: that person's bookings, oldest first | `test_pages_walk_every_booking_once_oldest_first` (25 interleaved with another email's) | smoke; probe T | verified |
| 38 | 4 | Email match ignores case | `test_the_email_match_ignores_case_and_spaces` | smoke (`  PAGER@example.COM `); probe T (`WALK@` vs `Walk@`) | verified |
| 39 | 4 | Cursor paging: `next_cursor` back as `cursor`; last page `null` | walk tests; `test_an_exact_multiple_ends_without_an_empty_page`; `test_bookings_made_at_the_same_instant_still_page_without_gaps` | smoke; probe T (3/3/2, last null) | verified |
| 40 | 4 | No duplicates, no gaps | walk tests compare the full id list to creation order | smoke; probe T | verified |
| 41 | 4 | `limit` 1–50, default 10; anything else 400 | `test_limit_accepts_1_to_50`, `test_any_other_limit_is_400[0/51/-1/abc/1.5/""]`, `test_the_default_page_size_is_10` | smoke (0/51/abc); probe U (11 values incl. ` 5`, fullwidth `１０`) | verified |
| 42 | 4 (spec) | Missing email / bad cursor → 400 | `test_the_email_is_required[*]`, `test_a_bad_cursor_is_400[*]` | smoke; probes V, W | verified |
| 43 | 4 (PRD) | Page: My Bookings, 10 per page, Next page until the end, cancelled greyed, cancel from the list, "No bookings for this email" | `npm test` (proxy) | headless Chromium (below) | verified |

**Test reality check:** every Level 4 test asserts the status and the body (`{"error": "<exact message>"}`, or full equality between first and replayed bodies), and the replay and race tests also count rows in Postgres. Schema: `alembic check` reports no drift between the models and migration 0001.

## Security pass (OWASP, Levels 1–4)

- **A01:** `GET /bookings` without a key is 401 (probe W). Note the design: anyone with the API key can list any email's bookings. That's the contract (one shared key, identified by email); the browser never holds the key, and the proxy is the only patient path.
- **A02:** API key 0 hits in either repo's history; only `.env.example` tracked.
- **A03:** the cursor is untrusted input: decoded, parsed into a datetime and a UUID, then used only as bound parameters in a SQLAlchemy `tuple_()` comparison. Garbage is 400, never a 500 (probe V). No string-built SQL.
- **A04:** the idempotency record is written in the same transaction as the booking; concurrent same-key requests serialise on the key's primary key (probe R: 20 → 1 booking). Keys are global (one API key exists) and kept until `/reset`.
- **A06:** `pip-audit` and `npm audit` clean.
- **A09:** 0 email addresses in the API logs; the 401 log line omits the query string.
- **DoS:** `limit` is capped at 50; keys at 255 characters.

## Commands run

```
$ make tests
collected 125 items
============================= 125 passed in 10.26s =============================
$ uv run ruff check && uv run ruff format --check
All checks passed!
45 files already formatted
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

All checks passed
$ BASE_URL=http://localhost:8070 uv run python scripts/concurrency.py
50 simultaneous bookings for one slot against http://localhost:8070
  finished in 0.63s
  201: 1
  409: 49
  winner: c615df25-fa90-4d9a-8cfd-224773ee862b (Racer 0), status confirmed
  slot 'race' available: False
PASS: exactly one booking won
$ (frontend) npm test
ℹ pass 5
ℹ fail 0
```

HTTP probes (`curl`, local API):

```
### P. same key + same body twice (curl -i), then the list
HTTP/1.1 201 Created
{"id":"77ed36b5-3ca0-4462-9a2c-db758bd9869c","slot_id":"v0","name":"Ada","email":"idem@example.com","status":"confirmed","created_at":"2026-10-26T03:02:19.860Z"}
HTTP/1.1 201 Created
{"id":"77ed36b5-3ca0-4462-9a2c-db758bd9869c","name":"Ada","email":"idem@example.com","status":"confirmed","slot_id":"v0","created_at":"2026-10-26T03:02:19.860Z"}
1 booking(s) in the list
### Q. same key, different body
HTTP/1.1 422 Unprocessable Entity
{"error":"Idempotency-Key reused with a different body"}
1 booking(s) in the list
### R. 20 parallel curl, same new key + body
   status       1 201201201201201201201201201201201201201201201201201201201201
   distinct ids: 1
1 booking(s) in the list
### S. replay after the booking was cancelled
{"id":"4d137518-1744-46ce-b84f-bbaf03b095ba","name":"Cy","email":"cy@example.com","status":"confirmed","slot_id":"v3","created_at":"2026-10-26T03:02:21.097Z"} [201]
{"id":"4d137518-1744-46ce-b84f-bbaf03b095ba","slot_id":"v3","name":"Cy","email":"cy@example.com","status":"cancelled","created_at":"2026-10-26T03:02:21.097Z"} [200] <- GET now
### T. walk 8 bookings for one email with limit=3 by next_cursor
   page 1: ['v4', 'v5', 'v6'] next_cursor: MjAyNi0xMC0yNlQw…
   page 2: ['v7', 'v8', 'v9'] next_cursor: MjAyNi0xMC0yNlQw…
   page 3: ['v10', 'v11'] next_cursor: null
### U. limit values
   limit=0                      {"error":"limit must be an integer from 1 to 50"} [400]
   limit=51                     {"error":"limit must be an integer from 1 to 50"} [400]
   limit=abc                    {"error":"limit must be an integer from 1 to 50"} [400]
   limit=-1                     {"error":"limit must be an integer from 1 to 50"} [400]
   limit=1.5                    {"error":"limit must be an integer from 1 to 50"} [400]
   limit=                       {"error":"limit must be an integer from 1 to 50"} [400]
   limit=%205                   {"error":"limit must be an integer from 1 to 50"} [400]
   limit=05                     [200] ok
   limit=1                      [200] ok
   limit=50                     [200] ok
   limit=%EF%BC%91%EF%BC%90     {"error":"limit must be an integer from 1 to 50"} [400]
### V. cursor values
   MjAyNi0xMC0yNlQwMzowMj   -> 3 bookings, next_cursor=set [200]
   MjAyNi0xMC0yNlQwMzowMj   -> cursor is not valid [400]
   MjAyNi0xMC               -> cursor is not valid [400]
   %00                      -> cursor is not valid [400]
   MjA5OS0wMS0wMVQwMDowMD   -> 0 bookings, next_cursor=null [200]
   (last one: a well-formed cursor for 2099, after every booking)
### W. email param variants
{"error":"email is required"} [400]
{"error":"email is required"} [400]
{"bookings":[],"next_cursor":null} [200]
{"error":"email is required"} [400] (no email param)
{"error":"invalid or missing API key"} [401] (no key)
### P2. key order: first response vs replay, raw bytes
   keys: ['id', 'slot_id', 'name', 'email', 'status', 'created_at']
   keys: ['id', 'name', 'email', 'status', 'slot_id', 'created_at']
   stored jsonb: {"id": "289c3ad7-1167-4ad1-8a23-0e52805b0c61", "name": "Ada", "email": "o@example.com", "status": "confirmed", "slot_id": "o1", "created_at": "2026-10-26T03:02:44.271Z"}
```

(R prints the 20 status codes run together because the parallel `curl` writes had no newlines between them: 20 × `201`, with 1 distinct booking id. V's second and third rows are the good cursor with an extra character, and cut short.)

Web page (headless Chromium via http://localhost:5180), security:

```
### web page: My Bookings (headless Chromium)
page 1: 10 rows | caption: Page 1 · oldest first · ada@example.com | Next page button: 1
  first row: Fri 1 Mar 2030, 09:00–09:30 · Dr Ade | 9d19935b-96ee-4230-9065-15a0a3154dd0 | Copy | confirmed | Cancel
page 2: 2 rows | Next page button: 0
all 12 once, oldest first: true | Bo's booking shown: false
cancel last row on page 2 -> status: cancelled | greyed: true
  slot list now shows m11 as: Choose
cancelled via Find a Booking -> My Bookings row says: cancelled
phone width horizontal scroll: false
nobody@example.com -> No bookings for this email.
blank email -> Please enter your email.
### secrets
.: key hits=0; tracked env: .env.example 
../clinic-booking-frontend: key hits=0; tracked env: .env.example 
### string-built SQL
none
### personal data in logs (emails)
0
### pip-audit
No known vulnerabilities found
### npm audit
found 0 vulnerabilities
```
