# Verification Report

**Scope:** level-1 (Koya Level 1: reset, list slots, book, look up a booking, plus the web page that sees slots, books one and shows the confirmation)
**Target:** local — API http://localhost:8070 (Docker Compose, 2 gunicorn workers, Postgres), page http://localhost:5180 (Vite dev server + `api/_proxy.js`). No deployed URL yet (deployment is slice 9).
**Date:** 2026-10-26
**Blockers:** 0
**Major:** 0
**Minor:** 3
**Verdict:** PASS
**Not verified:** deployed URL (doesn't exist yet, slice 9). Vercel's handling of `api/[...path].js` is not proven until it's deployed; the forwarding logic itself is covered by `npm test` and the dev server.

## Findings

| # | Severity | Level | Location | Finding | Why it matters | Remediation |
|---|---|---|---|---|---|---|
| 1 | minor | 1 | `src/core/timefmt.py` `format_slot_time` | Slot times are re-serialised, not echoed: a reset with `2026-12-10T09:00:00.000Z` comes back from `GET /slots` as `2026-12-10T09:00:00Z` (same instant; offsets also come back as UTC `Z`). | A checker that compares the returned string to the one it sent, rather than the instant, would see a mismatch — unlikely, since the contract's own example has no milliseconds and round-trips exactly. | **Resolved:** learner chose to keep UTC `Z` as in the contract example; recorded in `spec.md > Components > API: Slots`. |
| 2 | minor | 1 | `scripts/smoke.py` | Two Level 1 rules have tests but no smoke `check` line: "reset deletes every booking" and "reset keeps slots in the past". | The live smoke run in slice 9 won't prove these two on the deployed API, only the test suite will. | Add both checks to `smoke.py` (book, reset, `GET /bookings/{id}` → 404; reset with a past slot → listed). |
| 3 | minor | — | `.claude/skills/verify/SKILL.md` | The verify skill names the smoke script `scripts/smoke-test.sh`; the spec and the code use `scripts/smoke.py`. | A future verify run could wrongly report "missing smoke script". | **Fixed:** `verify` and `implement` skills now point at `scripts/smoke.py`. |

**Known and scheduled, not counted (out of Level 1 scope):**
- `POST /bookings` for an already-booked slot is a `500 {"error": "internal server error"}`: the partial unique index already blocks the second booking; mapping it to 409 is slice 4 (Level 3).
- `POST /bookings` with missing or non-string fields can be a 500; field validation is slice 3 (Level 2).
- No `X-API-Key` check yet, so `/reset` is open locally; auth is slice 3 (Level 2). Decide then whether `/docs` and `/openapi.json` stay key-free.

## Requirement map

| # | Level | Requirement (from task-1.md) | Test that proves it | Live check | Status |
|---|---|---|---|---|---|
| 1 | 1 | `POST /reset` → 200 | `test_reset_returns_ok` | smoke "POST /reset is 200"; curl #1 | verified |
| 2 | 1 | Reset deletes every booking | `test_reset_deletes_every_booking` | journey: admin reset → "Every booking was deleted" | verified (no smoke line, finding 2) |
| 3 | 1 | Reset replaces all slots, including slots in the past | `test_reset_keeps_past_slots_and_replaces_everything` | journey: past slot listed (greyed) | verified (no smoke line, finding 2) |
| 4 | 1 | Bad reset body → 400 `{"error"}` (contract: every error is `{"error"}`) | `test_reset_with_a_bad_body_is_400_in_the_error_shape` | curl #4 (bad JSON, empty, wrong type) | verified |
| 5 | 1 | `GET /slots`: every slot, earliest start first, shape `{slots:[{id,provider,start,end,available}]}` | `test_slots_are_listed_earliest_first_with_availability` | smoke; curl #1, #3 (ties ordered by id) | verified |
| 6 | 1 | `?provider=` exact match | `test_provider_filter_is_an_exact_match` | smoke; journey filter → 2 rows | verified |
| 7 | 1 | `available` false once booked | `test_a_booked_slot_is_listed_as_unavailable` | smoke "booked slot is now unavailable" | verified |
| 8 | 1 | `POST /bookings` → 201, status `confirmed`, body `{id,slot_id,name,email,status,created_at}` | `test_booking_a_slot_returns_201_confirmed` | smoke (incl. `created_at` ms + Z) | verified |
| 9 | 1 | Unknown slot → 404 `{"error"}` (listed under level 2, implemented now) | `test_booking_an_unknown_slot_is_404` | smoke | verified |
| 10 | 1 | `GET /bookings/{id}` → 200 booking | `test_a_booking_can_be_looked_up_by_id` | smoke; curl #8 | verified |
| 11 | 1 | `GET /bookings/{id}` unknown → 404 `{"error"}` | `test_an_unknown_booking_id_is_404` (UUID and non-UUID) | smoke | verified |
| 12 | 1 | Every error is `{"error": "<message>"}` (unknown route, wrong method, bad JSON, 500) | `test_unknown_routes_and_methods_keep_the_error_shape`, reset/booking 400 tests | curl #4–#7 (404, 405, 400, 500 all `{"error"}`) | verified |
| 13 | 1 | Bookings still there on the next request / after a restart | — (not unit-testable) | curl #9: `docker compose restart api`, same booking 200 | verified |
| 14 | 1 | Web page: see available slots, book one, see the confirmation | `npm test` (proxy key rules) | headless journey (below) + learner hands-on in slice 2 | verified |
| 15 | 1 | API key not in the browser bundle (`scope.md > Decisions Already Made`) | `npm test` | `grep` of `dist/` and dev-served modules: 0 hits (slice 2) | verified |

## Security pass (OWASP, Level 1 relevant)

- **A01 Access control:** no key check yet (Level 2, scheduled). The proxy never puts the server key on `/reset` (`npm test`, incl. `/reset/` and `//Reset`) and never follows redirects.
- **A02 Secrets:** `.env` / `.env.local` git-ignored; only `.env.example` tracked in both repos; the real API key appears 0 times in either repo's full history.
- **A03 Injection:** all queries via SQLAlchemy expressions, no string-built SQL. The page renders data through React (no `innerHTML` / `dangerouslySetInnerHTML`), so a booking name can't inject script.
- **A05 Misconfiguration:** 500 returns `{"error":"internal server error"}` with no stack trace (curl #6).
- **A06 Components:** `pip-audit` (locked deps) → no known vulnerabilities; `npm audit` → 0 vulnerabilities; both lockfiles committed.
- **A09 Logging:** only unhandled exceptions are logged; request bodies (names, emails) are not.

## Commands run

```
$ make tests
collected 15 items

tests/test_level1_slots_bookings.py ..............                       [ 93%]
tests/test_openapi_docs.py .                                             [100%]

============================== 15 passed in 0.96s ==============================
$ uv run ruff check && uv run ruff format --check
All checks passed!
31 files already formatted
$ make smoke
BASE_URL=${BASE_URL:-http://localhost:8070} uv run python scripts/smoke.py
Smoke test against http://localhost:8070

OK    GET /health is 200
OK    POST /reset is 200 {status: ok}
OK    GET /slots is 200, earliest first
OK    GET /slots marks free slots available
OK    GET /slots?provider= is an exact match
OK    POST /bookings is 201 confirmed
OK    booking created_at has milliseconds and Z
OK    GET /bookings/{id} returns the same booking
OK    the booked slot is now unavailable
OK    GET unknown booking is 404 {error}
OK    POST /bookings for an unknown slot is 404 {error}

All checks passed
$ (frontend) npm test
✔ patient requests get the server key, replacing any key the browser sent (76.147599ms)
✔ reset carries only the typed key, never the server key (11.652738ms)
✔ body, content type and Idempotency-Key are forwarded; redirects are not followed (2.150244ms)
✔ status, body and Retry-After come back unchanged (4.93565ms)
✔ an unreachable API is a 502 in the error shape (2.799592ms)
ℹ pass 5
ℹ fail 0
```

HTTP probes (`curl`, local API):

```
### 1. reset with the exact task-1 example, then GET /slots
HTTP/1.1 200 OK
{"status":"ok"}{"slots":[{"id":"s1","provider":"Dr Ade","start":"2026-12-10T09:00:00Z","end":"2026-12-10T09:30:00Z","available":true}]}
### 2. slot times sent with milliseconds (.000Z) - echoed back as sent?
{"slots":[{"id":"m1","provider":"Dr Ade","start":"2026-12-10T09:00:00Z","end":"2026-12-10T09:30:00Z","available":true}]}
### 3. same start time: tie order
{"slots":[{"id":"a","provider":"Y","start":"2026-12-10T09:00:00Z","end":"2026-12-10T09:30:00Z","available":true},{"id":"b","provider":"X","start":"2026-12-10T09:00:00Z","end":"2026-12-10T09:30:00Z","available":true}]}
### 4. reset: malformed JSON / no body / slots not a list
{"error":"request body is not valid JSON"} [400]
{"error":"Field required"} [400]
{"error":"slots: Input should be a valid list"} [400]
### 5. POST /bookings: malformed JSON, JSON array
{"error":"request body is not valid JSON"} [400]
{"error":"request body must be a JSON object"} [400]
### 6. 500 shape (double booking hits the index; 409 mapping is Level 3)
HTTP/1.1 500 Internal Server Error
content-type: application/json
{"error":"internal server error"}### 7. unknown route / wrong method
HTTP/1.1 404 Not Found
{"error":"not found"}HTTP/1.1 405 Method Not Allowed
{"error":"method not allowed"}### 8. GET /bookings/{id} with whitespace / uppercase uuid
id=f8d26ca0-3b42-48db-96fd-26aecaff0fd6
{"id":"f8d26ca0-3b42-48db-96fd-26aecaff0fd6","slot_id":"s1","name":"Ada Obi","email":"ada@example.com","status":"confirmed","created_at":"2026-10-26T01:38:32.854Z"} [200]
### 9. persistence: restart api, fetch again
HTTP/1.1 200 OK
{"id":"f8d26ca0-3b42-48db-96fd-26aecaff0fd6","slot_id":"s1","name":"Ada Obi","email":"ada@example.com","status":"confirmed","created_at":"2026-10-26T01:38:32.854Z"}
```

Web page, headless Chromium through http://localhost:5180 (`/api/*` via `api/_proxy.js`):

```
SLOT ROWS:
 Dr Bola | Mon 5 Jan 2026, 09:00–09:30 | Unavailable
 Dr Ade | Thu 10 Dec 2026, 10:00–10:30 | Choose
 Dr Ade | Thu 10 Dec 2026, 10:30–11:00 | Unavailable
 Dr Bola | Fri 11 Dec 2026, 15:00–15:30 | Choose
BOOKED ID: 3455f736-f3f6-4247-a006-1e904a262365
BOOKED ROW NOW: Dr Ade | Thu 10 Dec 2026, 10:00–10:30 | Unavailable
FOUND: Booking id | 3455f736-f3f6-4247-a006-1e904a262365 | Copy | Provider | Dr Ade | Time | Thu 10 Dec 2026, 10:00–10:30 | Name | Grace Hopper | Email | grace@example.com | Status | confirmed
UNKNOWN ID: No booking with that id.
FILTERED: 2 rows
RESET WITH TYPED KEY: Slots replaced. Every booking was deleted.
PHONE WIDTH horizontal scroll: false
CONSOLE ERRORS: [
  'Failed to load resource: the server responded with a status of 404 (Not Found)'
]
```

(The one console error is the deliberate lookup of the unknown id `nope`, which the browser logs as a failed 404 fetch.)

Security:

```
### secrets in git history (both repos)
.: key hits=0 ; env files ever tracked: 
../clinic-booking-frontend: key hits=0 ; env files ever tracked: 
### tracked .env files now
.env.example
.env.example
### raw SQL / string-built queries
none
### dangerous HTML in page
none
### logging of bodies
only core/errors.py logs (unhandled exceptions, no body)
$ uvx pip-audit -r <uv export --frozen --all-groups> --disable-pip --no-deps
No known vulnerabilities found
$ npm audit
found 0 vulnerabilities
```
