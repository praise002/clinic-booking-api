---
name: implement
description: Implement exactly one slice from docs/checklist.md for the clinic booking API, test-first - write the failing test from the slice's acceptance criterion and the Koya contract (task-1.md), then the minimal code to pass it, prove it with real pasted command output and a real HTTP call, tick the box, and commit. Refuses to write feature code until docs/scope.md, prd.md, spec.md and checklist.md are all approved. Use when asked to implement, build, code, or continue a specific slice or level ("build slice 3", "do the idempotency slice", "implement level 2", "what's next?"). A stricter, one-slice-at-a-time companion to 5-build; adapted from the Aellpr backend implement skills.
argument-hint: [slice number or title]
---

# implement — One slice, test first, proven

This project does not write feature code ahead of an approved plan. The planning skills (`2-scope`, `3-prd`, `4-spec`) and the build plan from `5-build` settle *what* and *how* first, so code doesn't get rewritten the moment a decision changes. So the first thing this skill does is check status, and it refuses to proceed if the plan isn't approved.

`5-build` plans the slices and can drive the whole build. Use `implement` when the learner wants to take one slice at a time with tighter discipline. Both read and write the same `docs/checklist.md`, so they never disagree about progress.

## Rule zero: disclose your own deviations

If you depart from this skill's process in any way, say so **at the top of your reply, before any success**, under `Process deviations this run`. This includes:

- skipping or reordering a step
- ticking a slice without real, pasted passing output behind it
- editing files outside this slice's scope
- running a different proof command than the one you announced
- discovering mid-run that `checklist.md` disagreed with what's actually in the code
- committing unrelated changes

If there were none, write `Process deviations this run: none.` Never omit it, and never put it after the summary. A deviation disclosed after the commit is disclosed too late to change anything.

## 1. Read the state, every run

Read `docs/checklist.md`, `docs/spec.md`, and `docs/learner-profile.md` before planning anything. If your memory of the state disagrees with the files, **the files win**; say so under deviations.

- `scope.md`, `prd.md`, `spec.md`, or `checklist.md` missing or not `status: approved` → name what's missing, point to the right skill, stop. Don't write code.
- Learn mode or fast mode is recorded in the checklist; carry it forward.

## 2. Pick and announce the slice

If the learner named one, work that one, and say so if an earlier slice it depends on is unticked. Otherwise take the first unchecked `- [ ]` slice.

Announce: the slice number and title, which Koya level and which `task-1.md` rules it covers, what you'll build, and the **exact proof command** you'll run. One slice per run.

## 3. Read the slice's context

1. The slice's fields: `Becomes usable:`, `PRD ref:`, `Spec ref:`, `Build:`, `Verify (mechanical):`, `Learner check:`, `Commit:`.
2. The referenced PRD and spec sections. The slice line is a pointer, not the spec.
3. The relevant part of `task-1.md`. It is the contract the Koya checker enforces: exact paths, status codes, field names, `{"error": "<message>"}` bodies, headers. When the PRD or spec seems to differ from it, stop and raise it; don't silently pick one.

## 4. Write the failing test first

Translate the requirement into a test that asserts the **status code and the response body/headers**, not just "no error". Stay within this slice's requirements; other slices cover the rest.

Run it. Confirm it fails **for the reason you expect** (route missing, wrong status), not an import error or typo. A test that fails for the wrong reason will also pass for the wrong reason.

Learn mode: before writing code, tell the learner in one or two sentences what the test checks and why it should fail right now.

## 5. Write the minimal implementation

Enough to pass the test, in the place `spec.md` says it belongs. Follow the spec's stack and structure; don't introduce a new library or layer the spec didn't agree on. If the spec doesn't say, ask; if asking would stall the run, take the smallest reversible option and record it under `spec.md > Decisions and Open Issues` the same run.

Properties of this task that are easy to "simplify" into a defect:

- **Every** response, including 401, 404 for unknown routes, and 500, is `{"error": "<message>"}` for errors.
- The API key check runs before validation on every route, including `/reset`.
- Trim `name` and `email`; store email lower-case; list-by-email matches case-insensitively.
- "No double booking" (level 3) must be enforced by the database (constraint, lock, or atomic conditional write), not by reading first and inserting after. A cancelled booking frees the slot.
- Idempotency (level 4) returns the *same status and booking id*, not just a similar one.
- The rate limit (level 5) counts failed attempts too, per normalized email, and `Retry-After` is whole seconds.
- Bookings persist across requests and restarts.

## 6. Prove it

A slice is never ticked on inspection. Reading the code you wrote is not proof; believing it works is not proof. Run real commands and paste their output **verbatim**.

| What you built | Proof |
|---|---|
| The slice's behavior | the test from step 4, now passing, by name |
| Nothing else broke | the full test suite and linter from `spec.md` |
| It works over HTTP | start the app and `curl -i` the endpoint with the right and wrong `X-API-Key`, showing status and body |
| Concurrency / idempotency / rate limit slices | the parallel or repeated requests that show it, not a sequential test alone |

- **Zero tests collected is a fail.**
- If a command can't run (no database, no network), the slice stays unticked with a note naming the exact command and why. That's a normal outcome; claiming success is not.
- If it fails, it's not done. Fix it, or stop and report. Never tick through a failure.

## 7. Smoke test, every slice

A green test suite proves this slice's behavior works *in isolation*. It doesn't prove the app actually boots and serves real requests: a bad environment variable, a migration that doesn't apply to a fresh database, a broken start command, or a route registered in the test setup but not the real app can all pass every test. **Every slice runs the smoke test after the suite, not just when something feels risky.**

`scripts/smoke.py` (named in `docs/spec.md`) is a plain HTTP script using httpx, so it can run against local and deployed URLs alike:

- Reads `BASE_URL` (default `http://localhost:<port from spec.md>`) and `API_KEY` from the environment. Never hardcode the real key.
- Starts from `POST /reset` with known slots (one in the past, a few in the future), so every run is repeatable.
- Has one `check` line per contract behavior built so far: method, path, headers, body, expected status, and a key fragment of the expected body. Prints `OK` or `FAIL` per line, and exits non-zero if any line fails.
- Always includes: a request with no key → `401`, an unknown route → `404` with `{"error": ...}`.

**Slice one creates the script** as part of its bootstrap (not as its own slice). **Every later slice adds `check` lines for the behavior it introduced** rather than checking by hand and leaving no trace. Paste the script's real `OK`/`FAIL` output; "it boots" is a claim, the per-line output is the proof.

Once the app is deployed, also run it with `BASE_URL=<deployed https URL>`. A deployment is only proven by a smoke test against the deployed URL.

A failing smoke test after a green suite is exactly what this step exists to catch. Don't tick the slice.

## 8. Learner check

Learn mode: explain what changed in the learner's vocabulary, give them the `Learner check:` (what to run or open, what to send, what they should see), and wait for their report. Point to the 2-3 lines of code responsible. If they hit a problem, fix it and re-prove before continuing. Fast mode: only at the checklist's planned hands-on checkpoints.

## 9. Tick, commit, report

1. Tick the slice `- [ ]` → `- [x]` in `docs/checklist.md`. Note any plan change under `## Revisions`.
2. Commit with the slice's `Commit:` message. Before committing, review the staged diff for secrets (API key, database URL), `.env`, and `docs/learner-profile.md`; stage only this slice's files. If there's no git repo yet, offer `git init` first.
3. Reply:

```
Process deviations this run: <none, or the list>

Slice: <N. title> (Koya level <n>)
Proof command: <exact command>
<pasted verbatim output>

HTTP check:
<pasted curl -i output>

Smoke test (<BASE_URL>):
<pasted OK/FAIL output>

Files changed: <list>
Checklist: <what was ticked or revised>
Commit: <sha and subject>

Next: <next unchecked slice>
```

Don't start the next slice unless asked: one slice is one reviewable unit. When a whole Koya level is done, suggest running `verify level-N` before moving on, since the task says to do each level properly before the next.
