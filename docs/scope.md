---
doc: scope
status: approved
---

# Clinic Booking API

A deployed clinic booking API that follows the Koya Task 1 contract exactly, plus a simple web page that exercises every endpoint it exposes.

## The Unique Kernel
The contract is fixed, so the distinctive part is not *what* the API does but *how solidly it holds*: "two people never book the same slot" is guaranteed by a mechanism the developer understands and has **proven** with 50 simultaneous bookings against one slot, not just argued for. The same standard of proof applies to idempotent retries and per-email rate limiting.

## Who It's For
- **Koya's automated checks**, which call the API at the deployed https URL and expect the contract in `task-1.md` to the letter (status codes, bodies, `{"error": ...}`, `X-API-Key`, `Retry-After`).
- **A patient at a small clinic (e.g. Dr Ade's)**, using the web page to find a free slot, book it, see the confirmation, and later find or cancel their booking.

## The Core Loop
A patient opens the page → sees available slots (optionally for one provider) → books one with name and email → sees the confirmation. Later they come back, look up their bookings by email (paging through them), and can cancel one, which frees the slot for someone else.

## Inspiration & Identity
Simple and plain: "nothing too fancy." Functional over polished.

## Why This Matters to the Learner
"Shipping this cleanly" and "clearing the levels solidly": each level done properly before the next. The main learning target is making "two people never book the same slot" actually hold under concurrent load, and understanding why the chosen mechanism works.

## What "Working" Looks Like
- All five levels pass against the contract.
- A test fires **50 simultaneous bookings at one slot**: exactly one gets 201, the rest get 409.
- A **smoke script run against the live https URL** passes end to end.
- The web page, on the deployed URL, can call every endpoint the API exposes: list slots, book, view a booking, cancel, list a person's bookings with paging.
- Bookings survive restarts (persistent storage).

## The POC Boundary
- Every endpoint and behaviour in `task-1.md`, Levels 1–5, built in level order and verified per level.
- Concurrency, idempotency and rate-limit guarantees each backed by a real test.
- A simple web page with a UI for every endpoint.
- Deployment at an https URL with a persistent database, plus a smoke script.

## Decisions Already Made
- **The API key stays on the server.** The browser never sees `X-API-Key`; the page talks to something server-side that adds it for patient actions (slots, book, look up, cancel, list).
- **Reset is gated by the key itself, not roles.** The page has a small admin section for `POST /reset`; whoever uses it types the API key, and that request carries their key, never the server's. Only key holders (the developer, Koya) can wipe data.

## Later
- Visual polish beyond a clean, plain page.

## Explicitly Cut
- Patient accounts / login: the contract identifies people by email only.
- RBAC / admin roles: one secret (the API key) is enough to protect reset.
- Demo video, Devpost submission, Discord post (per `CLAUDE.md`; replaced by deployed URLs, a live smoke test, and Koya's submission).
- Changing the deployment after submission, until Koya makes contact.
