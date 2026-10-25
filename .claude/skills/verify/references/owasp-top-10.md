# OWASP Top 10 (2021), mapped to the clinic booking API

Not every category applies to every level. Work the ones the scope touches. Stack-neutral on purpose: confirm each point against whatever `docs/spec.md` chose.

## A01 Broken Access Control

- **Every** route, including `/reset`, unknown routes, and error paths, requires `X-API-Key`. A missing or wrong key is `401` with `{"error": ...}`, checked *before* validation (otherwise an attacker learns which slot ids exist without a key).
- `/reset` wipes everything. It's in the contract and behind the API key, which is the intended control; just confirm it isn't reachable some other way (a second route, a debug endpoint).
- The web page: the API key must not be shipped to the browser in a way that hands it to anyone who views the source, unless the spec explicitly accepted that tradeoff for this assessment. If it is exposed, record the decision and its risk in `docs/spec.md > Decisions and Open Issues`.

## A02 Cryptographic Failures

- The API key and database URL come from environment variables, never committed. `.env` is git-ignored, `.env.example` has placeholders only.
- The key comparison is constant-time where the language offers it (e.g. `crypto.timingSafeEqual`, `hmac.compare_digest`).
- Served over HTTPS only (a contract rule too).

## A03 Injection

- All database access is parameterized. No SQL built by string concatenation from `slot_id`, `email`, `cursor`, `provider`, or `name`.
- The cursor is opaque but untrusted: a tampered or garbage cursor returns `400`, never a 500 or a query error.
- The web page escapes `name`/`provider` when rendering them (no `innerHTML` with user data), or a booking name like `<img onerror=...>` runs script for the next viewer.

## A04 Insecure Design

This is where most of this task's real risk lives. Read the design, not just the code.

- **Double booking (level 3)**: "check then insert" is a race. The guarantee must come from the database (a unique constraint on confirmed bookings per slot, a row lock, or an atomic conditional update), not from application code reading first. Cancelled bookings must not block re-booking.
- **Idempotency (level 4)**: the key-to-response record must be written atomically with the booking, or two concurrent retries can both create bookings. Decide and record: is the key scoped globally or per API key, and how long is it kept?
- **Rate limit (level 5)**: counted per normalized email (trimmed, lower-cased), failed attempts included. If the counter lives in memory, it resets on restart and isn't shared across serverless instances: confirm the hosting choice makes that acceptable, or store it in the database.
- **Time**: "slot has already started" compares against server UTC time, not the client's clock or a local timezone.

## A05 Security Misconfiguration

- No stack traces or framework error pages in responses. Every 4xx/5xx body is `{"error": "<message>"}`.
- Debug mode off in the deployed environment.
- CORS allows the web page's origin, and is not `*` with credentials.

## A06 Vulnerable and Outdated Components

- Run the stack's dependency audit. Lockfile committed.

## A07 Identification and Authentication Failures

- One fixed API key per the contract; there's no user login. Confirm the 401 message doesn't distinguish "missing" from "wrong" in a way that matters, and that the key isn't logged.

## A08 Software and Data Integrity Failures

- Dependencies installed from the lockfile in deployment.
- Request bodies parsed strictly: a non-JSON body or wrong types (`slot_id: 123`, `email: []`) return `400`, not a 500.

## A09 Security Logging and Monitoring Failures

- Emails and names are personal data: don't log full request bodies at info level. Log booking ids.
- 429s and 401s are logged enough to notice abuse.

## A10 Server-Side Request Forgery

- Not applicable unless the backend fetches a URL from input. It shouldn't.
