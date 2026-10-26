---
doc: checklist
status: approved
---

# Build Checklist

Build mode: learn

Slices follow Koya's levels in order (`scope.md > The POC Boundary`). Each level closes with `verify level-N` before the next level starts (`CLAUDE.md`). Slices 1–8 run locally: the API in Docker Compose, and the page on the Vite dev server, whose dev proxy adds the key as the Vercel function will. Deployment to Railway (API) and Vercel (page) is the last slice, by the learner's choice. Two repos: backend commits go to `clinic-booking-api`, frontend commits to `clinic-booking-frontend`.

## Slices

- [x] **1. Level 1 API: reset, list slots, book, look up — running locally on Postgres**
  Becomes usable: `docker compose up` starts api + Postgres. With curl you can `POST /reset` some slots, `GET /slots` (earliest first, `?provider=` exact match, `available` flag), `POST /bookings` → 201 confirmed, `GET /bookings/{id}` → the booking or 404. Every error is `{"error": ...}`. Data survives `docker compose restart api`.
  Why now: Bootstraps everything every later slice lands on: uv project, compose, Alembic, the domain layout, the global error shape, the test harness against real Postgres, `scripts/smoke.py`. The full `0001_initial` schema (including the partial unique index) goes in now because the spec defines it as one migration; its 409 behavior is proven in slice 4.
  PRD ref: `prd.md > API Contract`, `prd.md > Slots`, `prd.md > Admin Reset`
  Spec ref: `spec.md > Stack`, `spec.md > Where It Runs and How Someone Tries It` (Local), `spec.md > Components` (API: Error handling, API: Slots, API: Bookings steps 2/6/7/8 without validation, API: Booking lookup `GET /bookings/{id}`, API: Health), `spec.md > Data Model`, `spec.md > File Structure`
  Build: Scaffold per File Structure, mirroring `supportiq-ai-backend` (pyproject/uv, Dockerfile.dev, compose.yaml with postgres:17-alpine, Makefile, runner.sh, `.env.example`). Add config, async database session, Alembic async + `0001_initial`, `core/errors.py` + `core/timefmt.py`, the slots domain (`/reset`, `/slots`) and the bookings domain (`POST /bookings`, `GET /bookings/{id}`), `/health`. Then `tests/conftest.py` (test DB, truncate between tests), `tests/test_level1_slots_bookings.py`, and `scripts/smoke.py` with the Level 1 checks.
  Verify (mechanical): `make tests` passes. `docker compose up --build` starts clean on a fresh volume and migrations apply. `scripts/smoke.py` against `http://localhost:8070` prints all OK. curl a booking, `docker compose restart api`, and `GET /bookings/{id}` still returns it. `ruff check` is clean.
  Learner check: Run `docker compose up --build`. Reset with the `task-1.md` example slot, book `s1` with curl, copy the `id` from the 201, then fetch `/bookings/<id>`: you should see the same booking with `status: "confirmed"` and `created_at` ending in `Z`. `GET /slots` should now show `s1` with `available: false`.
  Commit: `Add Level 1 API: reset, slots, book, get booking`

- [x] **2. Level 1 web page: see slots, book one, see the confirmation, find it by id**
  Becomes usable: A local page (`npm run dev`, http://localhost:5180) where a patient sees every slot (readable times, provider filter, unavailable slots greyed), picks one, books it with name and email, gets a confirmation that leads with the booking id (with Copy), and can look the booking up by id. An Admin section resets slots with a typed key. Calls go to `/api/*`, which the Vite dev proxy forwards to the local API with the key added. The Vercel proxy function is written now too, but only deployed in slice 9.
  Why now: Completes Level 1 as `task-1.md` defines it ("plus a simple web page… see available slots, book one, and see the confirmation"). This is the early hands-on checkpoint, where your reaction to the look and flow can still shape the remaining sections.
  PRD ref: `prd.md > The Core Journey` (steps 1–4), `prd.md > Screens and Layout`, `prd.md > Look and Feel`, `prd.md > Slots`, `prd.md > Book a Slot`, `prd.md > Find a Booking`, `prd.md > Admin Reset`, `prd.md > States and Boundaries`
  Spec ref: `spec.md > Look and Feel`, `spec.md > Components` (Proxy: Vercel function, Web: API client, App shell, Slots section, Book a Slot, Find a Booking, Admin Reset), `spec.md > Where It Runs and How Someone Tries It` (Local, Frontend), `spec.md > File Structure` (`clinic-booking-frontend/`)
  Build: In `clinic-booking-frontend` (git init): Vite + React (JS), `styles.css` tokens, `vite.config.js` dev proxy with the key from `.env.local` (reset forwards the typed key, everything else gets the server key), `api/[...path].js` with the same rules plus 502 when unreachable, `api.js`, `format.js`, `messages.js`, App shell, SlotsSection, BookingForm (success path, disabled while in flight, generic failure message), FindBooking (no Cancel yet), BookingRow, AdminReset.
  Verify (mechanical): `npm run build` succeeds, and the built assets contain no API key (grep `dist/`). With the API and dev server running, curl `localhost:5180/api/slots`, `POST /api/bookings` and `/api/bookings/<id>` (the nested path), and confirm they return the API's bodies. Load the page with curl or a headless browser to confirm it renders.
  Learner check: Open http://localhost:5180. Reset slots from Admin with your key, pick an available slot, book it, and see the confirmation with the id first. The slot should turn grey. Paste the id into Find a Booking and see the same booking. Tell me what you notice about the look and flow, and what you'd change.
  Commit: `Add Level 1 web page and key-adding proxy` (frontend repo); then `verify level-1`

- [x] **3. Level 2: only key holders get in, and bad bookings are turned away**
  Becomes usable: Every route except `/health` returns `401 {"error": ...}` without the right `X-API-Key`. `POST /bookings` returns 400 for a missing, empty or non-string `slot_id`/`name`/`email`, an invalid email, or malformed JSON; 404 for an unknown slot; 400 for a slot that has already started. Name and email are stored trimmed and the email lower case. FastAPI's 422s, 404s and 405s all come out as `{"error": ...}` with the right status. On the page, each of these failures shows its plain-language message and keeps the form inputs, and an unreachable API shows "Couldn't reach the booking service".
  Why now: Level 2 per `task-1.md`. It also hardens the error shape that Koya's checks depend on before any more endpoints are added.
  PRD ref: `prd.md > API Contract`, `prd.md > Booking Errors` (400, started, 404), `prd.md > Admin Reset` (wrong key → "Wrong API key"), `prd.md > States and Boundaries` (API unreachable, Permissions)
  Spec ref: `spec.md > Components` (API: Auth middleware, API: Error handling, API: Bookings steps 1, 2, 5, 6; Web: Book a Slot error mapping, Web: Admin Reset), `spec.md > Important Failure Modes` (422 / non-error body leaks)
  Build: `core/auth.py` constant-time middleware (exempts `/health`, runs before routing), the 422→400 override plus 404/405/bad-JSON handlers, `bookings/pipes.py` validation and normalisation, slot-exists and slot-started checks, `tests/test_level2_auth_validation.py` asserting status **and** body shape for every error, smoke lines for Level 2. Frontend: `messages.js` mappings, BookingForm error display, slot refresh on 404/started.
  Verify (mechanical): `make tests` passes, including every Level 1 test, now sent with the key. Smoke passes locally, including no-key → 401 and bad-email → 400. A curl through the dev proxy (`localhost:5180/api/bookings`) with a bad email returns the 400 body.
  Learner check: On the page, try booking with an empty name, then `not-an-email`, then a slot in the past (reset one in from Admin). Each should give a clear message with your inputs still in the form. In Admin, try a wrong key and see "Wrong API key". Then `curl localhost:8070/slots` with no key and see a 401.
  Commit: `Add Level 2: API key auth and booking validation` (API repo), `Show booking error messages` (frontend repo); then `verify level-2`

- [x] **4. Level 3: two people can never book the same slot — proven with 50 at once**
  Becomes usable: A booking for a slot that already has a confirmed booking returns `409 {"error": "slot already booked"}`. 50 simultaneous requests for one slot give exactly one 201 and 49 409s, with no 5xx, leaving exactly one confirmed row, both in tests and against the running compose API with two gunicorn workers. On the page, a 409 says someone just booked the slot and refreshes the list.
  Why now: This is the unique kernel (`scope.md > The Unique Kernel`). It comes first in Level 3, as its own slice, so the proof isn't buried under cancel work. The partial unique index has existed since slice 1; this slice maps its violation to 409, sizes the connection pool, and proves that it holds.
  PRD ref: `prd.md > API Contract` (Concurrency), `prd.md > Booking Errors` (409)
  Spec ref: `spec.md > How This Works, In Plain Language`, `spec.md > Components` (API: Bookings step 7, API: Concurrency guarantee), `spec.md > Data Model` (`uq_bookings_slot_confirmed`), `spec.md > Important Failure Modes` (connection pool exhaustion)
  Build: Run the insert inside a SAVEPOINT in `bookings/repository.py`, mapping a unique violation on `uq_bookings_slot_confirmed` → `SlotAlreadyBooked` → 409. Set SQLAlchemy `pool_size`/`max_overflow` for the 50-way race. Add `tests/test_level3_concurrency_cancel.py` (the 50-way `asyncio.gather` proof: 1×201, 49×409, 0×5xx, 1 confirmed row), `scripts/concurrency.py` for any `BASE_URL`, and the 409 smoke line. Frontend: 409 message + slot refresh.
  Verify (mechanical): The concurrency test passes, run several times in a row so the pass isn't luck. `scripts/concurrency.py` against `http://localhost:8070` (gunicorn, `WEB_CONCURRENCY=2`) prints 1×201 / 49×409 and a single confirmed booking. Smoke passes.
  Learner check: Run `BASE_URL=http://localhost:8070 API_KEY=... uv run python scripts/concurrency.py` yourself and read the tally. Then explain back, in your own words, why the 49 losers get 409 instead of a second booking (which row they wait on, and what Postgres does when the first commits). If it isn't clear, we'll look at it together in psql.
  Commit: `Add Level 3: double-booking guarantee with 50-way concurrency proof`

- [ ] **5. Level 3: cancel a booking and the slot frees up**
  Becomes usable: `DELETE /bookings/{id}` → 200 with the cancelled booking. A second cancel → 409 "booking already cancelled". An unknown or non-UUID id → 404. After a cancel the slot shows `available: true` and can be booked again. Two simultaneous cancels give one 200 and one 409. On the page, Find a Booking gets a Cancel button with "are you sure?", which marks the row cancelled and refreshes the slots.
  Why now: Completes Level 3. It depends on slice 4's index: cancelling drops the row out of the partial index, which is what frees the slot.
  PRD ref: `prd.md > Cancel a Booking`, `prd.md > Find a Booking` (Cancel button), `prd.md > The Core Journey` (step 7)
  Spec ref: `spec.md > Components` (API: Booking lookup, list, cancel → `DELETE`; API: Concurrency guarantee, cancel→rebook test; Web: Cancel, Web: Find a Booking)
  Build: A conditional `UPDATE … WHERE status='confirmed' RETURNING *` in the repository, then the exists-check for 409 vs 404, the router, tests (cancel, re-cancel 409, unknown 404, cancel→rebook 201, two concurrent cancels), smoke lines. Frontend: `CancelButton.jsx`, wired into FindBooking.
  Verify (mechanical): `make tests` passes. Smoke passes, including book → cancel → rebook. Through the dev proxy, `DELETE /api/bookings/<id>` returns 200, then 409.
  Learner check: On the page, book a slot, find it by id, press Cancel and say no (nothing changes), then Cancel and yes. The row says cancelled and the slot is bookable again. Book it again to close the loop.
  Commit: `Add Level 3: cancel bookings` (API repo), `Add cancel to Find a Booking` (frontend repo); then `verify level-3`

- [ ] **6. Level 4: a retried booking never creates a duplicate**
  Becomes usable: `POST /bookings` with an `Idempotency-Key` header: repeating the same key and body returns the same status and the same booking id, and creates no second booking, even when the repeats arrive concurrently. The same key with a different body → `422 {"error": ...}`. Key order and whitespace in the body don't count as "different".
  Why now: The first half of Level 4. It touches the booking pipeline and transaction boundaries that slices 3–4 just settled, so it goes before paging, which is a read-only path.
  PRD ref: `prd.md > API Contract` (Idempotency)
  Spec ref: `spec.md > Components` (API: Idempotency, API: Bookings step 3), `spec.md > Data Model` (`idempotency_keys`), `spec.md > What Was Simplified and Why` (page doesn't send the key)
  Build: The `idempotency/` domain (claim with `INSERT … ON CONFLICT DO NOTHING RETURNING`, replay or 422, store the final 201/400/404/409 in the same transaction as the booking), the canonical body hash in `pipes.py`, and its wiring into the booking service. Add `/reset` wiping `idempotency_keys`, `tests/test_level4_idempotency_paging.py` (replay of 201 and of 409/400, 422 mismatch, 10 concurrent same-key requests → one booking, same id, checked by a direct DB count), smoke lines. API only, per the spec.
  Verify (mechanical): `make tests` passes. Smoke: two identical keyed POSTs return the same id, and a changed body with the same key → 422.
  Learner check: With curl against `localhost:8070`, send the same keyed booking twice and compare the two `id`s. Then change the name with the same key and see the 422.
  Commit: `Add Level 4: idempotent booking retries`

- [ ] **7. Level 4: page through a person's bookings, on the API and the page**
  Becomes usable: `GET /bookings?email=&limit=&cursor=` returns that person's bookings oldest first, case-insensitive, cancelled included, with `next_cursor` (`null` on the last page). It returns 400 for a missing email, a bad limit (not 1–50) or a bad cursor. On the page, the **My Bookings** section lists them 10 at a time with provider/time, id, status (cancelled greyed), **Next page**, and Cancel on confirmed rows. The core journey is now complete end to end.
  Why now: Completes Level 4, and with it the PRD's full core journey (book → find again → cancel → slot free).
  PRD ref: `prd.md > My Bookings`, `prd.md > Cancel a Booking`, `prd.md > The Core Journey` (steps 6–7)
  Spec ref: `spec.md > Components` (API: Booking lookup, list, cancel → `GET /bookings`; Web: My Bookings, Web: Cancel), `spec.md > Data Model` (`ix_bookings_email_page`)
  Build: Cursor encode/decode in `bookings/pipes.py`, a keyset page query fetching `limit+1`, the router and validation, and the paging tests in `test_level4_idempotency_paging.py` (multi-page walk with no gaps or repeats, case-insensitivity, limit bounds, bad cursor, the last page null). Add smoke lines. Frontend: `MyBookings.jsx` reusing BookingRow and CancelButton.
  Verify (mechanical): `make tests` passes. Smoke walks 3 pages of a 25-booking email and gets every id exactly once. Through the dev proxy, `/api/bookings?email=...` returns the page.
  Learner check: On the page, book three or more slots with one email, typing it in mixed case each time. Open My Bookings and see them oldest first. Cancel one and see it greyed. If you have more than 10, use Next page. Try an email with no bookings.
  Commit: `Add Level 4: list bookings by email with cursor paging` (API repo), `Add My Bookings section` (frontend repo); then `verify level-4`

- [ ] **8. Level 5: no one can spam bookings**
  Becomes usable: A 6th `POST /bookings` attempt for one email within a rolling 60 seconds (failed attempts included) returns `429 {"error": ...}` with an integer `Retry-After` in 1–60. Other emails are unaffected, keyed replays aren't counted, `/reset` clears the limits, and if Redis is down the API fails open. On the page, a 429 shows how many seconds to wait.
  Why now: Level 5, the last level. Redis enters the stack only here, so the earlier levels never depended on it.
  PRD ref: `prd.md > API Contract` (Rate limit), `prd.md > Booking Errors` (429)
  Spec ref: `spec.md > Components` (API: Rate limiting, API: Bookings step 4, API: Slots `/reset` clears `ratelimit:*`), `spec.md > Data Model` (Redis), `spec.md > Important Failure Modes` (Redis down)
  Build: Add `redis` to compose, `redis_client.py`, and the `ratelimit/` domain with `sliding_window.lua`. Wire it after idempotency and before validation, add the `/reset` key clear and fail-open with a logged warning. Add `tests/test_level5_rate_limit.py` (5 failing + 6th → 429 with valid `Retry-After`, another email OK, replay not counted, Redis-down fail-open) and smoke lines. Frontend: the 429 message with `retryAfter`; both the dev proxy and the Vercel function forward `Retry-After`.
  Verify (mechanical): `make tests` passes (the whole suite, all levels). Smoke and `scripts/concurrency.py` pass locally. Through the dev proxy, the 6th attempt returns 429 with a `Retry-After` header. Stopping the redis container still lets a booking through. `ruff check` is clean.
  Learner check: On the page, try booking six times quickly with the same email (bad details are fine; they count). The sixth says how many seconds to wait. Then book with a different email straight away and it works.
  Commit: `Add Level 5: per-email rate limiting with Redis` (API repo), `Show rate-limit wait time` (frontend repo); then `verify level-5`

- [ ] **9. Live: the API on Railway and the page on Vercel, proven at their https URLs**
  Becomes usable: The API at a Railway https URL, backed by Railway Postgres and Redis. The page at a Vercel https URL, calling the API through the key-adding function. Smoke and the 50-way concurrency proof pass against the live API, and bookings survive a redeploy. The README lists both URLs and explains how each guarantee works.
  Why now: Deployment is last, by the learner's choice. Everything it ships has already passed all five levels locally. Expect to resolve the deploy unknowns here (`spec.md > Decisions and Open Issues`, "To verify"): the `railway/iac` version, the `DATABASE_URL` scheme rewrite and asyncpg SSL, preDeploy migrations, the plan's resource limits, and whether Vercel's catch-all matches nested paths.
  PRD ref: `prd.md > API Contract` (survives a restart, smoke against the live URL), `prd.md > What We're Building`, `prd.md > States and Boundaries` (Permissions)
  Spec ref: `spec.md > Where It Runs and How Someone Tries It` (Deployed), `spec.md > External Services and Dependencies`, `spec.md > Important Failure Modes` (Vercel catch-all), `spec.md > File Structure` (`.railway/`, `Dockerfile`, `api/[...path].js`)
  Build: Two-stage uv `Dockerfile` and `.railway/railway.ts` mirroring `supportiq-ai-backend`: Postgres + Redis plugins, `api` service, `preDeploy: alembic upgrade head`, healthcheck `/health`, env `API_KEY`/`DATABASE_URL`/`REDIS_URL`/`WEB_CONCURRENCY=2`, plus the `postgresql://` → `postgresql+asyncpg://` rewrite in settings. Deploy the frontend to Vercel with `API_BASE_URL` and `API_KEY`. If the catch-all fails on nested paths, switch to the `api/proxy.js` + `vercel.json` rewrite fallback and record it. Finish both READMEs. You do the Railway and Vercel logins and set the `API_KEY` secrets; I write the config and run the checks.
  Verify (mechanical): The Docker image builds and runs locally first. Railway deploy succeeds and `/health` returns 200 over https. `BASE_URL=<railway url> scripts/smoke.py` prints all OK, and `scripts/concurrency.py` against it prints 1×201 / 49×409. Book once, trigger a redeploy, and the same `GET /bookings/{id}` still returns it. On the Vercel URL, curl `/api/slots`, `/api/bookings/<id>` (the nested path) and a 6th rate-limited attempt (429 + `Retry-After`) through the function. The deployed bundle contains no API key.
  Learner check: Open the Vercel URL and walk the whole journey: reset from Admin, book, find it by id, see it in My Bookings, cancel it, and see the slot free again. Run the smoke script against the Railway URL yourself and watch every line say OK.
  Commit: `Deploy API to Railway` (API repo), `Deploy web page to Vercel` (frontend repo); then `verify` for the whole build

## Hands-on Checkpoints

- [x] Early usable behavior explored — after slice 2 (the Level 1 page running locally): look, flow and copy feedback that shapes slices 3–9. Done: learner reset, booked, copied the id and found it, filtered by provider; "it works as expected", no changes requested.
- [ ] Final kick-the-tires exploration and feedback completed — on the deployed URLs, after slice 9

## Final Review

- [ ] Final review complete — feedback resolved and learner confirms ready to ship

## Code Tour and App Map

- [ ] Learning activity complete — guided route, focused alternative, prior practice connected, or brief recap
- [ ] Optional edit and transfer reflection addressed — offered/declined/already covered/not applicable as appropriate
- [ ] `docs/app-map.html` generated from finished code, checked, and shown, including a project-grounded practice to reuse

Activity and evidence: [what actually happened; real document/test/code references; unfinished work if interrupted]
Route and stops: [actual paths and symbols; guided stops completed, or reference-only route]
Edit outcome: [tried/kept/reverted/declined/not applicable; verification if changed]
Reflection: [offered/answered/declined/already covered — personal answer belongs only in the ignored profile]
Activity mode: [live app and editor, explicit static fallback, focused alternative, prior practice, or recap]

## Revisions

- Local ports are 8070 (api) and 5452 (Postgres), not 8000/5432; checklist and spec updated — other local containers on this machine already hold 8000, 8010, 5432 and 5442.
- The whole global error shape (validation → 400, unknown route 404, wrong method 405, bad JSON 400, 500 → `{"error"}`) and the unknown-slot 404 moved into slice 1 — Level 1 already needs `{"error"}` bodies and a 404 for a missing slot (otherwise the foreign key turns it into a 500). Slice 3 still adds the auth, field validation, started-slot check and the per-error tests.
- Every endpoint now carries full OpenAPI docs (summary, description, every response status with an example; FastAPI's auto 422 removed), guarded by `tests/test_openapi_docs.py` — the learner asked for it after slice 1. Each later slice documents the statuses and endpoints it adds (401, 409, 422, 429 + `Retry-After`).
- The dev proxy is a small Vite plugin that calls the same `api/_proxy.js` `forward()` as the Vercel function, instead of Vite's built-in `server.proxy`; the dev server runs on 5180 (5173 is taken locally). Local testing therefore exercises the exact proxy code that deploys, and its key rules are covered by `npm test` (`node --test`, no extra dependencies).
- `make up_build` now passes `--renew-anon-volumes` — adding `email-validator` in slice 3 showed compose keeps the old anonymous `/app/.venv` volume on rebuild, so new dependencies were invisible in the container.
- The API docs (`/docs`, `/redoc`, `/openapi.json`) are public alongside `/health`, with the key entered through Swagger's Authorize box — the learner first chose key-protected docs, found a browser can't send the header, and switched. Endpoints and unknown routes still need the key.
- The booking form sets `noValidate`, so every validation message comes from the API (one source of truth) rather than the browser's own email bubble.

