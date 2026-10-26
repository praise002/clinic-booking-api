---
doc: spec
status: approved
---

# Clinic Booking API — Technical Spec

## How This Works, In Plain Language

There are three running pieces and two data stores:

1. **The API** (`clinic-booking-api`, FastAPI on Railway). It implements the `task-1.md` contract exactly. Every route except `/health` requires `X-API-Key`.
2. **The web page** (`clinic-booking-frontend`, a Vite + React app on Vercel). It is one page with five stacked sections. It runs in the patient's browser, so it never holds the API key.
3. **The proxy** (one Vercel serverless function inside the frontend repo). The page calls `/api/...` on its own domain. The function forwards the call to Railway with the server's API key added, then returns the API's status, body and `Retry-After` untouched. For `/reset` only, it forwards the key the admin typed and never adds its own.
4. **PostgreSQL** (Railway). It holds slots, bookings and idempotency records. It is the source of truth and survives restarts.
5. **Redis** (Railway). It holds the per-email rate-limit log: timestamps of recent booking attempts, which expire after a minute.

**The double-booking guarantee lives in the database, not in Python.** A partial unique index allows at most one row with `status = 'confirmed'` per `slot_id`. When 50 requests race for one slot, Postgres makes every insert after the first wait for that first transaction. Once it commits, the rest fail with a unique violation, which the API turns into 409. Application code never does "check if free, then insert", which is the pattern that breaks under load. Cancelling sets the status to `cancelled`, the row drops out of the index, and the slot can be booked again.

**Why this shape:**
- The API stays a pure implementation of the contract.
- The key-hiding job sits in a tiny proxy instead of bending the API.
- Redis does the one job it's good at (short-lived counters shared across the API's worker processes).
- Postgres does everything that must be correct and durable.

In-memory locks or counters would break as soon as gunicorn runs two workers, so nothing that must be shared lives in process memory.

## The Core Journey Through the System

PRD ref: `prd.md > The Core Journey`.

```
Browser (React) ──/api/*──▶ Vercel function ──X-API-Key──▶ FastAPI (Railway) ──▶ Postgres
                                                                         └──▶ Redis (rate limit)
```

1. **The patient opens the page.** React requests `GET /api/slots`. The Vercel function adds `X-API-Key` and calls Railway's `GET /slots`. FastAPI reads `slots` left-joined with confirmed `bookings` and returns them earliest first, with `available = (no confirmed booking)`. React formats the times in the browser's timezone, and greys out slots that are unavailable **or** have `start <= now`.
2. **They filter by provider.** The dropdown is built from the unfiltered slot list. Picking a provider calls `GET /api/slots?provider=Dr%20Ade`.
3. **They choose a slot.** This is browser-only: the Book a Slot form shows that slot's provider and time.
4. **They press Book.** React sends `POST /api/bookings {slot_id, name, email}` and disables the button. The proxy forwards it. FastAPI then:
   1. checks the key;
   2. parses the JSON;
   3. handles `Idempotency-Key`, if sent;
   4. records the attempt in Redis and rejects the 6th one in a minute with 429;
   5. validates and normalises the body;
   6. checks the slot exists and hasn't started;
   7. inserts the booking.

   If another confirmed booking holds the slot, the unique index makes the insert fail → 409. On 201, React shows the confirmation (booking id first) and re-fetches the slots.
5. **The booking fails.** React maps the status to a plain message (`prd.md > Booking Errors`). On 409, 404 or a "slot started" 400, it re-fetches the slots. On 429, it shows the `Retry-After` seconds.
6. **The patient returns: My Bookings.** `GET /api/bookings?email=...&limit=10` returns bookings oldest first, plus `next_cursor`. React looks up each `slot_id` in the unfiltered slot list it already holds to show provider and time. **Next page** sends `cursor=<next_cursor>`.
7. **They cancel.** After the "are you sure?" step, `DELETE /api/bookings/{id}` runs. FastAPI flips the status to `cancelled` in one conditional `UPDATE`. React marks the row cancelled and re-fetches the slots, so the slot shows as available again.

## Stack

All choices below were agreed in the `4-spec` conversation. Library versions are pinned in `uv.lock` / `package-lock.json` when installed. Versions weren't looked up during planning, so use the current stable release of each at install time.

**Backend** (`clinic-booking-api`, Python 3.12, uv, mirrors `supportiq-ai-backend`)

| Piece | Choice | Why | Docs |
|---|---|---|---|
| Framework | FastAPI | Learner's main stack | https://fastapi.tiangolo.com |
| Server | gunicorn + `uvicorn.workers.UvicornWorker` (`scripts/runner.sh`) | Same as SupportIQ. Two workers, which is exactly why shared state must live in Postgres/Redis | https://www.uvicorn.org/deployment/ |
| DB access | SQLAlchemy 2 (async) + asyncpg | Async, matches the learner's style skill | https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html |
| Migrations | Alembic (async template) | Holds the partial unique index as versioned schema | https://alembic.sqlalchemy.org |
| Config | pydantic-settings | `API_KEY`, `DATABASE_URL`, `REDIS_URL` from env | https://docs.pydantic.dev/latest/concepts/pydantic_settings/ |
| Email validation | `email-validator` (`check_deliverability=False`) | Syntax check without DNS lookups | https://github.com/JoshData/python-email-validator |
| Redis client | `redis` (redis-py, `redis.asyncio`) | Rate-limit sorted sets + Lua script | https://redis.readthedocs.io/en/stable/ |
| Tests | pytest, pytest-asyncio, httpx (`ASGITransport`) against real Postgres + Redis from compose | The concurrency proof needs a real database | https://www.python-httpx.org/advanced/transports/ |
| Lint/format | ruff | Same as SupportIQ | https://docs.astral.sh/ruff/ |
| Local runtime | Docker Compose from day one: `api`, `db` (`postgres:17-alpine`), `redis` (`redis:7-alpine`) | Learner's choice | https://docs.docker.com/compose/ |

**Frontend** (`clinic-booking-frontend`, sibling folder, its own git repo)

| Piece | Choice | Why | Docs |
|---|---|---|---|
| Build | Vite | Learner's choice | https://vite.dev/guide/ |
| UI | React, **JavaScript** (no TypeScript) | Learner's choice | https://react.dev |
| Styling | One plain CSS file with custom-property tokens, no UI library | "Nothing too fancy" | — |
| Proxy | Vercel Node.js function `api/[...path].js` | Keeps `X-API-Key` server-side | https://vercel.com/docs/functions |

## Where It Runs and How Someone Tries It

### Local

**Backend:**

```bash
cp .env.example .env            # set API_KEY
docker compose up --build       # api on http://localhost:8070, db, redis
docker compose exec api alembic upgrade head   # runner.sh also runs this on start
make tests                      # pytest against the compose db/redis (test database)
```

- **Smoke test:** `BASE_URL=http://localhost:8070 API_KEY=... uv run python scripts/smoke.py`
- **Concurrency against any URL:** `BASE_URL=... API_KEY=... uv run python scripts/concurrency.py` (fires 50 simultaneous bookings at one slot and asserts 1×201 + 49×409).

**Frontend:**
- Run `npm install && npm run dev`, then open http://localhost:5180.
- In dev, `vite.config.js` proxies `/api/*` to `http://localhost:8070` and adds the key from `.env.local` (`API_KEY`, no `VITE_` prefix, so it never enters the bundle). Production behaves the same way, through the Vercel function.

### Deployed (required, `CLAUDE.md`)

- **API on Railway:** project `clinic-booking-api`, defined as code in `.railway/railway.ts` (`railway/iac`, the same pattern as `supportiq-ai-backend`):
  - `postgres("Postgres")` and `redis("Redis")` plugins.
  - One `api` service, `builder: "DOCKERFILE"`, `preDeploy: "alembic upgrade head"`, `healthcheck: "/health"`, restart `ON_FAILURE`.
  - Env: `API_KEY` (a Railway secret, `preserve()`), `DATABASE_URL` (from `db.env.DATABASE_URL`, rewritten to the `postgresql+asyncpg://` scheme in settings), `REDIS_URL`, `WEB_CONCURRENCY=2`.
  - Railway supplies the https URL.
- **Web page on Vercel:** import the `clinic-booking-frontend` repo, framework preset Vite. Set the env vars `API_BASE_URL` (the Railway https URL) and `API_KEY`. Vercel supplies the https URL.
- **Proof on the live URLs** (`6-ship`): run `scripts/smoke.py` and `scripts/concurrency.py` against the Railway URL, click through the deployed page, and redeploy or restart the API to confirm bookings survive. After submission, change nothing.

## Look and Feel

From `prd.md > Look and Feel` and `scope.md > Inspiration & Identity`: plain and "clinic colour".

- **Tokens** (in `src/styles.css`):
  - `--bg: #ffffff`, `--surface: #f5f8fa`, `--border: #e3e8ee`
  - `--text: #1f2933`, `--muted: #6b7280` (unavailable and cancelled states)
  - `--accent: #0f766e` (teal buttons and links), `--accent-hover: #115e59`
  - `--danger: #b42318` (errors), `--success: #067647`
- **Type:** `system-ui` stack at 16px base. Booking ids in a monospace face with a **Copy** button.
- **Layout:** a single centred column, `max-width: 720px`, 24px between sections, each section with an `h2`. It works at phone width with 16px side padding.
- **Rows, not cards.** Unavailable and cancelled rows are greyed (`--muted`) and carry a text label, not just a colour. No hero banner, gradients, animation or shadows.
- **Copy tone:** short, plain sentences that say what to do next ("Someone just booked this slot. Please pick another.").

## Components

### API: Auth middleware
- Rejects any request whose `X-API-Key` is missing or not equal to `settings.API_KEY`, returning `401 {"error": "invalid or missing API key"}`. It uses a constant-time compare.
- Exempt: `/health` (Railway healthcheck) and the API docs (`/docs`, `/redoc`, `/openapi.json`). It runs before routing, so unknown paths also return 401 without a key.
- PRD ref: `prd.md > API Contract`, `prd.md > Admin Reset`.

### API: Error handling
- One global handler set turns every error into `{"error": "<message>"}`.
- FastAPI's default 422 for request validation is **overridden to 400**. 422 is reserved for the idempotency mismatch only.
- Malformed JSON → 400. Unknown route → 404. Wrong method → 405. All in the same error shape.
- Domain exceptions (`SlotNotFound`, `SlotStarted`, `SlotAlreadyBooked`, `BookingNotFound`, `BookingAlreadyCancelled`, `IdempotencyKeyMismatch`, `RateLimited`) are mapped in `errors.py`. Services never raise `HTTPException`.
- PRD ref: `prd.md > API Contract`.

### API: Slots (`POST /reset`, `GET /slots`)
- **`POST /reset`:**
  - Validates `{"slots": [{id, provider, start, end}]}`. A non-empty string `id` and `provider`, ISO 8601 datetimes, and unique ids; otherwise 400.
  - In one transaction: deletes `idempotency_keys`, `bookings` and `slots`, then inserts the new slots (past ones included).
  - Then clears every Redis `ratelimit:*` key.
  - Returns `200 {"status": "ok"}`.
- **`GET /slots?provider=`:** exact match. Ordered by `start_at, id`. `available` is `true` unless the slot has a confirmed booking (agreed in `4-spec`; a slot that has started but isn't booked still shows `available: true`).
- **Datetimes** are returned in UTC with a `Z` suffix, e.g. `2026-12-10T09:00:00Z`, with fractional seconds only when non-zero. They are re-serialised, not echoed: `09:00:00.000Z` or `10:00:00+01:00` comes back as `09:00:00Z` (learner decision after `verify level-1`: follow the contract example's format).
- PRD ref: `prd.md > Slots`, `prd.md > Admin Reset`.

### API: Bookings (`POST /bookings`)

The order inside one request:

1. **Auth** (middleware).
2. **Parse JSON.** If the body isn't a JSON object → 400.
3. **Idempotency** (only if the `Idempotency-Key` header is present; see **API: Idempotency**). This can end the request early with a replay or a 422.
4. **Rate limit** (only if `email` is a non-empty string). Record the attempt for `email.strip().lower()`. If it's the 6th in 60 seconds → `429`, with `Retry-After` and no further work. See **API: Rate limiting**.
5. **Validate.** `slot_id`, `name` and `email` must be present, strings, and non-empty after trimming, and the email must be syntactically valid → else 400. Store `name` trimmed and `email` trimmed + lower case.
6. **Slot checks.** Unknown slot → 404. `start_at <= now()` → `400 {"error": "slot has already started"}`.
7. **Insert** inside a SAVEPOINT. A unique violation on `uq_bookings_slot_confirmed` → `409 {"error": "slot already booked"}`.
8. **Return** `201` with the booking: `id`, `slot_id`, `name`, `email`, `status: "confirmed"` and `created_at` with milliseconds and `Z`.

Booking ids are UUIDv4 strings. PRD ref: `prd.md > Book a Slot`, `prd.md > Booking Errors`, `prd.md > API Contract`.

### API: Concurrency guarantee
- **Mechanism:** the partial unique index `uq_bookings_slot_confirmed ON bookings (slot_id) WHERE status = 'confirmed'` (Alembic migration 0001). It is the only thing preventing double booking. There's no pre-check SELECT to race against.
- **Proof:** `tests/test_concurrency.py` fires 50 `POST /bookings` for one slot with `asyncio.gather`, through httpx `ASGITransport` against the real compose Postgres. It asserts exactly one 201, 49 409s, and one confirmed row. `scripts/concurrency.py` repeats this against the deployed URL.
- A second test asserts cancel → rebook succeeds, which proves the index frees the slot.
- PRD ref: `prd.md > API Contract` (Concurrency).

### API: Idempotency
- **Storage:** the Postgres table `idempotency_keys`, written **in the same transaction** as the booking, so a key and its booking can't be half-saved.
- **Flow,** for a request with key `K`:
  - `INSERT INTO idempotency_keys (key, body_hash) VALUES (K, H) ON CONFLICT DO NOTHING RETURNING key`.
  - **Inserted (first use):** continue with steps 4–8. Then store `status_code` and `response` on the row and commit.
  - **Conflict:** this means another request already used `K`; a concurrent one blocks on the primary key until the first commits. Read the row. A different `body_hash` → `422 {"error": "Idempotency-Key reused with a different body"}`. The same hash → replay the stored status and body exactly (same booking id).
- **`body_hash`:** SHA-256 of the parsed JSON re-serialised with sorted keys and no whitespace. "Same body" therefore means same fields and values, regardless of key order or formatting.
- **What gets stored:** final outcomes 201, 400, 404 and 409. **Not stored:** 429 and 401, because the transaction rolls back and the key row disappears, so a later retry gets a real attempt.
- **Replays** don't count as rate-limit attempts and can't be blocked by 429 (agreed in `4-spec`).
- **Retention:** until the next `/reset`.
- PRD ref: `prd.md > API Contract` (Idempotency).

### API: Rate limiting
- **Storage:** Redis. The window is sliding: 5 attempts per rolling 60 seconds per normalised email.
- **One Lua script, atomic in Redis,** on the key `ratelimit:{email}`:
  - `ZREMRANGEBYSCORE` entries older than now − 60 s.
  - `ZCARD`. If it's ≥ 5, return the oldest score.
  - Otherwise `ZADD` now (with a unique member) and `PEXPIRE` 60 s.
- **Rejection:** if the script returns an oldest score, respond `429 {"error": "too many booking attempts, try again later"}` with `Retry-After: max(1, ceil(oldest + 60 − now))`.
- **Counting:** every attempt with an email string counts, whatever its later outcome (400, 404, 409, 201). Other emails have separate keys, so they're unaffected.
- **Redis unavailable:** fail open (log a warning and allow the booking). Booking correctness never depends on Redis.
- **Proof:** a test makes 5 failing attempts plus a 6th, asserts 429 and an integer `Retry-After` in 1–60, and checks that another email still gets through.
- PRD ref: `prd.md > API Contract` (Rate limit), `prd.md > Booking Errors` (429).

### API: Booking lookup, list, cancel
- **`GET /bookings/{id}`:** returns the booking, or `404 {"error": "booking not found"}`. A non-UUID id is also 404, never 422.
- **`GET /bookings?email=&limit=&cursor=`:**
  - `email` is required → else 400. It's matched against `lower(trim(email))`.
  - `limit` must be an integer from 1 to 50, default 10 → else 400.
  - Ordered by `(created_at, id)` ascending.
  - `cursor` is base64url of `"<created_at ISO>|<id>"`, so the next page is `WHERE (created_at, id) > (c_at, c_id)`. An undecodable cursor → 400.
  - The API fetches `limit + 1` rows to decide `next_cursor`; it's `null` on the last page.
  - Cancelled bookings are included.
- **`DELETE /bookings/{id}`:**
  - Runs `UPDATE bookings SET status = 'cancelled' WHERE id = :id AND status = 'confirmed' RETURNING *` and returns `200` with the cancelled booking.
  - If no row was updated: if the booking exists → `409 {"error": "booking already cancelled"}`, else 404.
  - It's atomic, so two simultaneous cancels give one 200 and one 409.
- PRD ref: `prd.md > Find a Booking`, `prd.md > My Bookings`, `prd.md > Cancel a Booking`.

### API: Health
- `GET /health` → `200 {"status": "ok"}`. No key needed. Used by the Railway healthcheck only.

### Proxy: Vercel function
- `api/[...path].js` in the frontend repo.
- **Forwarding:** for `${API_BASE_URL}/${path}${search}` it forwards the method, the JSON body, `Content-Type` and `Idempotency-Key`.
  - For `reset`: it forwards the client's `X-API-Key` header as-is and **never** adds the server key.
  - For everything else: it drops any client-sent key and sets `X-API-Key: process.env.API_KEY`.
- **Response:** it returns the upstream status, the JSON body and `Retry-After` unchanged. If the upstream can't be reached → `502 {"error": "booking service unreachable"}`.
- PRD ref: `prd.md > States and Boundaries` (Permissions), `scope.md > Decisions Already Made`.

### Web: API client (`src/api.js`)
- One `request(method, path, {body, query, apiKey})` wrapper over `fetch('/api/...')`.
- It returns `{ok, status, data, retryAfter}`.
- It maps network failures to `{ok: false, status: 0}`, which the UI shows as "Couldn't reach the booking service, please try again".

### Web: App shell (`src/App.jsx`)
- Owns the shared state: `allSlots` (unfiltered, used for the provider dropdown and the slot lookups in My Bookings) and `selectedSlot`.
- Exposes `refreshSlots()`, which every section calls after a change.
- Renders the five sections in the order given in `prd.md > Screens and Layout`.

### Web: Slots section (`src/components/SlotsSection.jsx`)
- Provider dropdown ("All providers" plus the distinct providers from `allSlots`). The list comes from `GET /slots?provider=`.
- Rows show provider and `Thu 10 Dec 2026, 09:00–09:30` (`Intl.DateTimeFormat`, browser timezone), with no slot id.
- A slot is bookable when `available && start > now`.
- Empty states: "No slots yet" / "No slots for this provider". Plus "Loading…".
- PRD ref: `prd.md > Slots`, `prd.md > States and Boundaries`.

### Web: Book a Slot (`src/components/BookingForm.jsx`)
- Shows the form for `selectedSlot` and disables Book while a request is in flight.
- The confirmation shows the booking id (monospace + Copy), provider, time, name, email and status.
- Error messages are mapped from status: 409 / 400 / 400-started / 404 / 429 (with `retryAfter` seconds) / unreachable. The inputs keep their values.
- PRD ref: `prd.md > Book a Slot`, `prd.md > Booking Errors`.

### Web: Find a Booking (`src/components/FindBooking.jsx`)
- Id input → `GET /bookings/{id}`, shown as a booking row.
- Unknown id: "No booking with that id".
- A confirmed booking has a Cancel button (shared `CancelButton`).
- PRD ref: `prd.md > Find a Booking`.

### Web: My Bookings (`src/components/MyBookings.jsx`)
- Email input → `GET /bookings?email=&limit=10`.
- **Next page** uses `next_cursor` and replaces the shown page with the next one. The PRD defers "previous page".
- Each row shows provider and time (looked up from `allSlots` by `slot_id`, or "Slot no longer listed" if missing), the booking id and the status.
- Cancelled rows are greyed. Empty: "No bookings for this email".
- PRD ref: `prd.md > My Bookings`.

### Web: Cancel (`src/components/CancelButton.jsx`)
- `window.confirm("Are you sure you want to cancel this booking?")` → `DELETE /bookings/{id}`.
- On 200 it updates the row in place and calls `refreshSlots()`. On 409: "This booking is already cancelled".
- PRD ref: `prd.md > Cancel a Booking`.

### Web: Admin Reset (`src/components/AdminReset.jsx`)
- Inputs: an API key (`type="password"`) and a slots JSON textarea, pre-filled with the `task-1.md` example.
- `JSON.parse` runs client-side first ("That isn't valid JSON").
- A confirm step ("This deletes every booking."), then `POST /api/reset` with the typed key.
- 401: "Wrong API key". On 200: success, then `refreshSlots()`.
- PRD ref: `prd.md > Admin Reset`.

## Data Model

Postgres (Alembic `0001_initial`):

```sql
CREATE TABLE slots (
  id        text PRIMARY KEY,           -- client-supplied via /reset, e.g. "s1"
  provider  text NOT NULL,
  start_at  timestamptz NOT NULL,
  end_at    timestamptz NOT NULL
);
CREATE INDEX ix_slots_start ON slots (start_at, id);
CREATE INDEX ix_slots_provider ON slots (provider);

CREATE TABLE bookings (
  id          uuid PRIMARY KEY,
  slot_id     text NOT NULL REFERENCES slots(id) ON DELETE CASCADE,
  name        text NOT NULL,
  email       text NOT NULL,            -- stored trimmed + lower case
  status      text NOT NULL CHECK (status IN ('confirmed', 'cancelled')),
  created_at  timestamptz NOT NULL DEFAULT now()
);
-- THE double-booking guarantee:
CREATE UNIQUE INDEX uq_bookings_slot_confirmed ON bookings (slot_id) WHERE status = 'confirmed';
CREATE INDEX ix_bookings_email_page ON bookings (email, created_at, id);

CREATE TABLE idempotency_keys (
  key          text PRIMARY KEY,
  body_hash    text NOT NULL,
  status_code  int,
  response     json,                     -- json, not jsonb: keeps key order (0002)
  created_at   timestamptz NOT NULL DEFAULT now()
);
```

Redis: `ratelimit:{email}`, a sorted set of attempt timestamps (ms). It expires 60 s after the last attempt.

**Where each piece of data lives:**

| Data | Lives in | Updated by | After leaving and coming back |
|---|---|---|---|
| Slots | Postgres `slots` | `/reset` only | Same slots |
| Bookings | Postgres `bookings` | `POST /bookings` (insert), `DELETE` (status flip), `/reset` (wipe) | Same bookings, survive restarts |
| Idempotency records | Postgres `idempotency_keys` | First request with a key; wiped by `/reset` | Same replay |
| Rate-limit attempts | Redis | Each booking attempt; cleared by `/reset` | Gone after 60 s (by design) |
| Page state (selected slot, typed email, current page) | React state in the browser | User actions | Gone; the page remembers nothing (`prd.md > States and Boundaries`) |
| API key (server's) | Railway env + Vercel env | Set by hand | Never sent to the browser |

## File Structure

```
koya-assessment/
├── clinic-booking-api/                 # this repo
│   ├── .railway/
│   │   ├── package.json                # { "railway": "3.11.0" }, as in supportiq
│   │   └── railway.ts                  # IaC: Postgres, Redis, api service, env, preDeploy, healthcheck
│   ├── src/
│   │   ├── main.py                     # app factory: middleware, error handlers, routers, /health
│   │   ├── config.py                   # pydantic-settings: API_KEY, DATABASE_URL, REDIS_URL
│   │   ├── database.py                 # async engine/session, get_session dependency
│   │   ├── redis_client.py             # redis.asyncio client, get_redis dependency
│   │   ├── core/
│   │   │   ├── auth.py                 # X-API-Key middleware (exempts /health)
│   │   │   ├── exceptions.py           # AppError base class
│   │   │   ├── errors.py               # global handlers → {"error": ...}; 422→400 override
│   │   │   └── timefmt.py              # UTC "Z" datetime formatting
│   │   ├── slots/
│   │   │   ├── router.py               # POST /reset, GET /slots
│   │   │   ├── service.py              # reset (transaction + clear rate limits), list
│   │   │   ├── repository.py
│   │   │   ├── models.py               # Slot ORM
│   │   │   ├── schemas.py              # ResetRequest, SlotResponse, SlotListResponse
│   │   │   └── exceptions.py
│   │   ├── bookings/
│   │   │   ├── router.py               # POST/GET /bookings, GET/DELETE /bookings/{id}
│   │   │   ├── service.py              # the booking pipeline (steps 2–8), list, cancel
│   │   │   ├── repository.py           # insert (savepoint, unique-violation → SlotAlreadyBooked), cancel UPDATE, page query
│   │   │   ├── models.py               # Booking ORM (+ partial unique index declared)
│   │   │   ├── schemas.py              # BookingResponse, BookingListResponse
│   │   │   ├── pipes.py                # normalise/validate fields, cursor encode/decode
│   │   │   ├── constants.py            # DEFAULT_LIMIT=10, MAX_LIMIT=50
│   │   │   ├── enums.py                # BookingStatus
│   │   │   └── exceptions.py
│   │   ├── idempotency/
│   │   │   ├── service.py              # claim key / replay / mismatch, store result
│   │   │   ├── repository.py
│   │   │   ├── models.py
│   │   │   └── pipes.py                # canonical body hash
│   │   └── ratelimit/
│   │       ├── service.py              # check_and_record(email) → None | retry_after
│   │       ├── constants.py            # LIMIT=5, WINDOW_SECONDS=60
│   │       └── sliding_window.lua
│   ├── migrations/                     # Alembic (async); versions/0001_initial.py
│   ├── tests/
│   │   ├── conftest.py                 # test DB + Redis, truncate between tests, AsyncClient
│   │   ├── test_level1_slots_bookings.py
│   │   ├── test_level2_auth_validation.py
│   │   ├── test_level3_concurrency_cancel.py   # the 50-concurrent proof
│   │   ├── test_level4_idempotency_paging.py
│   │   └── test_level5_rate_limit.py
│   ├── scripts/
│   │   ├── runner.sh                   # alembic upgrade head (unless --skip-migrations) + gunicorn
│   │   ├── smoke.py                    # end-to-end contract walk against BASE_URL
│   │   └── concurrency.py              # 50 simultaneous bookings against BASE_URL
│   ├── Dockerfile                      # two-stage uv build, as in supportiq (no extras)
│   ├── Dockerfile.dev                  # dev image used by compose
│   ├── compose.yaml                    # api, db (postgres:17-alpine), redis (redis:7-alpine)
│   ├── Makefile                        # up, down, mig, mmig, tests, lint, format
│   ├── pyproject.toml / uv.lock
│   ├── alembic.ini
│   ├── .env.example
│   ├── task-1.md                       # the normative contract
│   ├── docs/                           # planning docs
│   └── README.md                       # live URLs, how to run, how the guarantees work
│
└── clinic-booking-frontend/            # separate repo, deployed to Vercel
    ├── api/
    │   └── [...path].js                # the key-adding proxy (Vercel function)
    ├── src/
    │   ├── main.jsx
    │   ├── App.jsx                     # shared slot state, section order
    │   ├── api.js                      # fetch wrapper → {ok, status, data, retryAfter}
    │   ├── format.js                   # slot time formatting
    │   ├── messages.js                 # status → plain-language message
    │   ├── styles.css                  # tokens + layout
    │   └── components/
    │       ├── SlotsSection.jsx
    │       ├── BookingForm.jsx
    │       ├── FindBooking.jsx
    │       ├── MyBookings.jsx
    │       ├── BookingRow.jsx
    │       ├── CancelButton.jsx
    │       └── AdminReset.jsx
    ├── index.html
    ├── vite.config.js                  # dev proxy /api → localhost:8070 with API_KEY from .env.local
    ├── .env.example                    # API_BASE_URL, API_KEY (server-side only)
    ├── package.json
    └── README.md
```

## External Services and Dependencies

- **Railway** (API, Postgres, Redis): https://docs.railway.com.
  - Config as code: `railway/iac` via `.railway/railway.ts`, following `supportiq-ai-backend`. It is TypeScript, not the `railway.toml` file format; see https://docs.railway.com/reference/config-as-code.
  - Secrets: `API_KEY`.
  - Cost: the learner's existing Railway plan. Check the plan covers three always-on resources.
  - Railway's `DATABASE_URL` uses `postgresql://`, so settings rewrite it to `postgresql+asyncpg://`.
- **Vercel** (web page + proxy function): https://vercel.com/docs/frameworks/vite, https://vercel.com/docs/functions.
  - Env: `API_BASE_URL`, `API_KEY`. Free Hobby plan.
- **Koya's checks** call the Railway URL directly with their key. They never go through Vercel.

## Important Failure Modes

- **The Vercel catch-all function route doesn't match nested paths** (`/api/bookings/abc`) in a non-Next project. Verify on the first frontend deploy. → Fallback: a single `api/proxy.js` plus a `vercel.json` rewrite `"/api/(.*)" → "/api/proxy?path=$1"`.
- **The FastAPI default 422 or a non-`{"error"}` body leaks through** (validation errors, 404/405, bad JSON) and breaks Koya's checks. → Global handlers plus a test per level that asserts the body shape on every error status.
- **Redis is down** → the rate limit fails open with a logged warning, and bookings still work and stay correct.
- **The API is unreachable from the page** → the proxy returns 502 and the page shows "Couldn't reach the booking service, please try again" instead of a blank section.
- **The connection pool is exhausted during the 50-way race** → set the SQLAlchemy `pool_size`/`max_overflow` so 50 concurrent requests queue rather than error, and the test asserts that there are no 5xx responses.

## What Was Simplified and Why

- **No UI library or TypeScript on the frontend**: plain CSS and JavaScript, per "nothing too fancy" and the learner's choice.
- **Next-page-only paging**: the contract's cursor only goes forward (`prd.md > Deferred From the POC`).
- **The page doesn't send `Idempotency-Key`**: double submits are prevented by disabling the button. Idempotency is proven by API tests, `smoke.py` and Koya's checks. Adding it to the page would need a key-per-attempt policy that complicates retry-after-correction (same key + corrected body = 422).
- **Idempotency records are kept until `/reset`**, not given a TTL. This is fine at POC volume. A real system would expire them after about 24 h.

## Decisions and Open Issues

**Learner decisions (`4-spec`):**
- FastAPI + PostgreSQL, with Docker from the start.
- A React frontend (Vite, JavaScript) on Vercel and the API on Railway, with Railway set up as code like `supportiq-ai-backend`.
- A Vercel serverless function as the key-adding proxy (accepted over a key-free FastAPI route, which would have defeated Level 2).
- Concurrency via a **partial unique index** (accepted over `SELECT … FOR UPDATE` and SERIALIZABLE isolation): the guarantee lives in the schema, so no code path can forget it.
- Rate limiting in **Redis** (chosen over the recommended Postgres option).
- **Idempotent replays** don't count toward the rate limit and can't be blocked by 429. The order is: idempotency, then rate limit.
- **`available` is false only when a slot has a confirmed booking**. The page greys out started slots by itself. This resolves the first item in `prd.md > Open Questions`.
- Rate limiting uses a **sliding** 60-second window (a sorted set + Lua script), confirmed at review.
- Rate limiting **fails open** when Redis is down, confirmed at review.
- `/reset` also clears the **rate-limit keys** and idempotency records, confirmed at review.

- **The API docs load without the key** (`/docs`, `/redoc`, `/openapi.json`), alongside `/health`; every endpoint, and any unknown route, still needs it (learner decision in slice 3, after trying the strict version). The OpenAPI schema declares the `X-API-Key` scheme, so Swagger's **Authorize** box takes the key for trying endpoints, and documents a 401 on every endpoint but `/health`.

**Implementation details derived from those choices (agent defaults, change freely):**
- 429 and 401 are never stored as idempotent responses.
- `/health` is exempt from the key.
- UUIDv4 booking ids and an opaque `(created_at, id)` cursor.
- My Bookings resolves provider and time from the page's unfiltered slot list. This resolves the second item in `prd.md > Open Questions`.

**Learner uncertainty:** none was raised. The learner chose the partial unique index without naming an unclear part. The one thing to keep confirming is *why* it holds: the explanation under **How This Works, In Plain Language** (concurrent inserts wait on the index entry, then fail). The evidence will be `test_level3_concurrency_cancel.py` and `scripts/concurrency.py` against the live URL: exactly one 201, 49 409s, one confirmed row.

**To verify in the deployment slice** (deployment is the last build slice, by the learner's choice in `5-build`):
- The Vercel catch-all route behaviour (see **Important Failure Modes**).
- The current `railway/iac` API, compared with the `3.11.0` used in supportiq.
- Railway's plan limits for Postgres + Redis + api.
- Whether Railway's `DATABASE_URL` needs `?sslmode` handling with asyncpg on the private network.
