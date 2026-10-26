# Clinic Booking API

A booking API for a small clinic: list appointment slots, book one, look a booking up, cancel it, and page through a person's bookings. Built for Koya Cohort 4, Task 1, against the contract in [`task-1.md`](task-1.md). All five levels are done.

| | |
|---|---|
| **API** | https://clinic-booking-api-indol.vercel.app (Vercel + Neon Postgres + Upstash Redis) |
| **API docs** | https://clinic-booking-api-indol.vercel.app/docs (the bare URL redirects there; no key needed to read them; press **Authorize** and enter the key to try endpoints) |
| **Web page** | https://clinic-booking-frontend-1pyf.vercel.app ([`clinic-booking-frontend`](../clinic-booking-frontend)) |

Every request except `GET /health` (and the docs) needs the `X-API-Key` header. Every error is `{"error": "<message>"}`.

## Endpoints

| Method | Path | Level | Does |
|---|---|---|---|
| `POST` | `/reset` | 1 | Replaces all slots (past ones included), deletes every booking, and clears idempotency keys and rate-limit counts |
| `GET` | `/slots?provider=` | 1 | Every slot, earliest start first, with `available` (false once it has a confirmed booking). `provider` is an exact match |
| `POST` | `/bookings` | 1–5 | Books a slot. `201` confirmed. `400` bad details or slot already started, `404` unknown slot, `409` already booked, `422` `Idempotency-Key` reused with a different body, `429` + `Retry-After` after 5 attempts a minute for one email |
| `GET` | `/bookings/{id}` | 1 | One booking, or `404` |
| `DELETE` | `/bookings/{id}` | 3 | Cancels it (`200`) and frees the slot. `409` if already cancelled, `404` if unknown |
| `GET` | `/bookings?email=&limit=&cursor=` | 4 | That person's bookings, oldest first, cancelled ones included. `limit` 1–50 (default 10). Pass `next_cursor` back as `cursor`; `null` on the last page |
| `GET` | `/health` | — | `200 {"status": "ok"}` for the host's healthcheck |

## How the guarantees work

Each one is enforced by a data store in a single step, never by "read, then decide, then write" in Python. With two worker processes, read-then-write is exactly the pattern two simultaneous requests slip through.

**No double booking (Level 3).** A partial unique index allows one *confirmed* booking per slot:

```sql
CREATE UNIQUE INDEX uq_bookings_slot_confirmed ON bookings (slot_id) WHERE status = 'confirmed';
```

There's no "is it free?" query. When two inserts race, Postgres makes the second wait on the first's uncommitted index entry. If the first commits, the second fails on the index and the API answers `409`. If the first rolls back, the second goes through. Cancelling sets `status = 'cancelled'`, so the row leaves the index and the slot can be booked again. Cancelling is one conditional `UPDATE … WHERE status = 'confirmed'`, so two simultaneous cancels give one `200` and one `409`.

Proof: 50 simultaneous bookings for one slot give exactly 1×`201` and 49×`409`, in a test and live (`scripts/concurrency.py`). With the index dropped, the same test gives 50×`201`.

**Retries never duplicate (Level 4).** The `Idempotency-Key` is claimed with `INSERT … ON CONFLICT DO NOTHING` **in the same transaction as the booking**. The final response (`201`, `400`, `404` or `409`) is stored on the key row, and both commit together. A retry with the same key and body gets that stored response back, byte for byte. A different body gets `422`. Simultaneous retries wait on the first's key row, then replay it. A `401` or `429` is never stored, so a later retry gets a real attempt. Keys are kept until `/reset`.

**Paging (Level 4).** Keyset pagination on `(created_at, id)`: the next page is "everything after the last row returned", not "skip N". New bookings can't make rows repeat or vanish between pages, and `id` breaks ties between bookings made at the same instant. The cursor is opaque base64url; anything the API didn't make is a `400`.

**Rate limit (Level 5).** At most 5 attempts per email (trimmed, lower case) in any rolling 60 seconds, failed attempts included. One Lua script on Redis drops old attempts, counts, and records the new one atomically, using Redis's clock so both workers agree. The 6th attempt gets `429` with `Retry-After` in whole seconds. Replays of an `Idempotency-Key` don't count and are never refused. If Redis is unreachable, bookings go ahead with a logged warning (0.5 s timeout): the rate limit guards against spam, and correctness lives in Postgres.

## Run it locally

Needs Docker and [uv](https://docs.astral.sh/uv/).

```bash
cp .env.example .env          # set API_KEY
make up_build                 # api on http://localhost:8070, Postgres on 5452, Redis on 6396
make tests                    # 146 tests against the compose Postgres and Redis
make smoke                    # the whole contract over HTTP (wipes local data)
export $(grep ^API_KEY .env)
BASE_URL=http://localhost:8070 uv run python scripts/concurrency.py   # the two races
```

The local ports avoid ones already taken on the developer's machine; change them in `compose.yaml`.

## Tests and proof

- `tests/test_level{1..5}_*.py`: one file per Koya level, against a real Postgres and Redis. Each asserts the status code **and** the exact body. The race tests count rows directly in Postgres.
- `tests/test_openapi_docs.py`: every endpoint documents its summary, description and every response.
- `scripts/smoke.py`: 45 checks over HTTP against any `BASE_URL`, covering all five levels.
- `scripts/concurrency.py`: 50 simultaneous bookings for one slot, then 20 simultaneous retries with one `Idempotency-Key`, against any `BASE_URL`.
- `docs/verification.md`: the latest independent check of every requirement, with the commands' real output.

## Deploy (free: Vercel + Neon + Upstash)

The API runs on **Vercel** as one Python function (`[tool.vercel] entrypoint = "src.main:app"` in `pyproject.toml`, region `iad1` in `vercel.json`). Postgres is on **Neon** and Redis on **Upstash**, all on free plans in US East. The step-by-step guide, including signing up for each, is [`docs/deploy.md`](docs/deploy.md). In short:

```bash
DATABASE_URL="<neon direct url>" uv run alembic upgrade head   # once
npx vercel link && npx vercel env add …                       # API_KEY, DATABASE_URL (pooled), REDIS_URL (rediss://)
npx vercel deploy --prod
BASE_URL=https://<api> API_KEY=<key> uv run python scripts/smoke.py
```

Hosting details the code handles:
- **Neon URLs** (`?sslmode=require&channel_binding=require`) work as copied: `src/db_options.py` turns them into asyncpg's `ssl` setting.
- **Neon's pooler** (a `-pooler` host, transaction mode) gets asyncpg's and SQLAlchemy's statement caches turned off, with unique statement names. Tested behind a local PgBouncer with prepared-statement support off: without this, the 50-way race fails with `DuplicatePreparedStatementError`; with it, both races pass.
- **Idle connections:** `pool_pre_ping` and a 5-minute recycle replace connections Neon dropped while it slept.

The Docker/gunicorn setup (`Dockerfile`, `scripts/runner.sh`, `.railway/railway.ts`) still works for container hosts such as Railway, and is what `docker compose` runs locally.

## Layout

```
src/
  main.py            app, middleware, OpenAPI tweaks, /health
  config.py          settings from the environment
  core/              API key middleware, {"error"} handlers, time formatting
  slots/             POST /reset, GET /slots
  bookings/          the booking pipeline, lookup, cancel, paging
  idempotency/       claim / replay / 422 for Idempotency-Key
  ratelimit/         the sliding-window Lua script and the per-email limiter
migrations/          Alembic: 0001 schema (incl. the partial unique index), 0002 json responses
src/db_options.py    database URL handling for hosts (Neon sslmode, poolers)
scripts/             runner.sh, smoke.py, concurrency.py
docs/                scope, PRD, spec, build checklist, verification report, deploy guide
.claude/skills/      the workflow skills (planning, build, implement, verify, ship) for Claude Code
.agents/skills/      the same skills for other coding agents; AGENTS.md mirrors CLAUDE.md
```
