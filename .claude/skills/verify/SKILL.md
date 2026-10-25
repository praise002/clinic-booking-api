---
name: verify
description: Independently check whether the clinic booking API is actually finished for a given level (1-5) or for the whole build. Cross-checks every requirement in the Koya contract (task-1.md) and every acceptance criterion in docs/prd.md against real, passing tests and real HTTP calls, runs the project's test/lint commands from docs/spec.md, does a security pass (see references/owasp-top-10.md), and writes a severity-ranked report to docs/verification.md. Reports only; never fixes code unless invoked with --fix. Use when asked to verify, audit, close out, sign off, or check a level ("is level 3 done?", "verify the booking endpoint", "are we safe to submit?", "run security checks"). Adapted from the Aellpr backend verify skills.
argument-hint: [level-N | all] [--fix]
---

# verify — Is it really done?

A ticked box in `docs/checklist.md` means someone believed a slice was finished when they ticked it. It does not mean the test still exists, still passes, or ever covered what it claimed. This skill does not take that on faith. The Koya checks will hit the deployed API with exact requests and compare exact responses, so "it looks right" is worth nothing here.

This skill **reports**. A check that quietly repairs what it is measuring is not a check.

## Rule zero: disclose your own deviations

If you depart from this skill's process in any way, say so **at the top of your reply, before any verdict**, under `Process deviations this run`. This includes:

- reporting a requirement as verified without opening the test or making the call
- auditing only part of the requested scope without saying so
- being unable to run a command the audit depends on
- writing any file other than `docs/verification.md` without `--fix`

If there were none, write `Process deviations this run: none.` Never omit the line, and never put it after the verdict.

## Learning mode

Read `docs/learner-profile.md` if it exists. For each finding, add one plain-language sentence on *why it matters* (what a real patient or the Koya checker would hit). The point is that the learner understands each gap, not just that a list exists. Don't lecture; one sentence per finding.

## 1. Fix the scope

Default scope is every level implemented so far (per `docs/checklist.md`). With `level-N`, audit that level plus everything below it, since levels build on each other (level 3's 409 still needs level 2's 401). State the scope in the report header.

## 2. Build the requirement → proof map

Source of truth, in order: `task-1.md` (the Koya contract, normative), then `docs/prd.md` (acceptance criteria), then `docs/spec.md` (how it was built). If prd or spec disagrees with `task-1.md`, that disagreement is itself a `major` finding.

List every rule in scope from `task-1.md` as its own row: each endpoint, each status code, each validation rule, each header. For example, level 2 alone yields rows for: missing key → 401, wrong key → 401, missing `slot_id` → 400, empty `name` → 400, invalid email → 400, unknown slot → 404, slot already started → 400, name and email trimmed, email lower-cased. Then for each row, find what proves it:

| # | Level | Requirement (from task-1.md) | Test that proves it | Live check | Status |
|---|---|---|---|---|---|

Flag immediately, before running anything: any requirement with **no** test, and any checklist slice that claims a requirement but is unticked.

## 3. Confirm the tests are real

For every test named in the map, open the file and confirm the test exists and actually asserts the requirement (the status code *and* the body shape, not just "no exception"). A renamed or missing test means the requirement is **not verified**, whatever the checkbox says.

## 4. Run it

Run the test and lint commands from `docs/spec.md` (`Where It Runs and How Someone Tries It`, or the project manifest). Paste the output **verbatim**: don't summarize, retype, or paraphrase a pass.

- **Zero tests collected is a fail**, not a pass.
- If a command cannot run (no database, no network), say which and why, and mark the affected rows `not verified`. Never infer a pass from unrun tooling.

Then **run `scripts/smoke-test.sh`**, every time, against local and (once it exists) the deployed URL via `BASE_URL`. Paste the real `OK`/`FAIL` output. A green suite with a failing smoke test is **not verified**: report it as a finding, not a footnote. Also check the script itself: every requirement row in scope should have a `check` line, and a missing one is a `minor` finding (a `major` one for a level-3+ behavior). A missing script is a `major` finding.

Then **exercise the running app over HTTP** beyond what the smoke script covers (local, and the deployed URL once one exists): `POST /reset`, then the requests that prove each row, with `curl -i` so status codes and headers are visible. Paste the output. Pay special attention to the things unit tests most often miss:

- **Level 3 concurrency**: fire many simultaneous `POST /bookings` at the same slot (e.g. 20 parallel `curl` calls, or a short script) and confirm exactly one `201` and the rest `409`. A sequential test does not prove this.
- **Level 4 idempotency**: same key + same body twice → identical status and booking id, one booking in the list; same key + different body → `422`. Also send the same key concurrently.
- **Level 4 pagination**: walk every page with `next_cursor` until `null`; no duplicates, no gaps, oldest first, `limit` of `0`, `51`, and `abc` all `400`.
- **Level 5 rate limit**: 5 attempts for one email (including failing ones) then the 6th is `429` with an integer `Retry-After`; a different email in the same minute is unaffected.
- **Persistence**: bookings survive a restart / a new request on a fresh serverless instance.
- **Error shape**: every error, including 404 for unknown routes and 500s, is `{"error": "<message>"}`.

## 5. Security pass

Read `references/owasp-top-10.md` and work the categories relevant to the scope. Also run the stack's dependency audit if one exists (e.g. `npm audit`, `pip-audit`) and scan the diff and git history for committed secrets (the API key, database URLs).

## 6. Severity

| Severity | Meaning |
|---|---|
| `blocker` | The Koya checker would get a wrong status code or body, data can be lost or double-booked, or a secret is exposed. |
| `major` | A real defect or contract deviation that a careful checker or user would hit. |
| `minor` | Style, clarity, naming, missing explanation. |

Don't inflate to look thorough, don't deflate to clear a gate.

## 7. Write `docs/verification.md`

Overwrite each run. Header first and exact:

```markdown
# Verification Report

**Scope:** <level-N or all levels so far>
**Target:** <local and/or deployed URL>
**Date:** <YYYY-MM-DD>
**Blockers:** <n>
**Major:** <n>
**Minor:** <n>
**Verdict:** <PASS if blockers is 0, otherwise FAIL>
**Not verified:** <none, or what and why>

## Findings

| # | Severity | Level | Location | Finding | Why it matters | Remediation |
|---|---|---|---|---|---|---|

## Requirement map

<the table from step 2, with final status>

## Commands run

<verbatim output>
```

## 8. --fix

Only with `--fix`: fix `blocker` and `major` findings written in this same run, re-run the proofs, paste the output, update the report counts. If a fix needs a decision the contract or spec doesn't settle, don't guess: leave it open and ask. Explain each fix to the learner in a sentence.

## Reply shape

```
Process deviations this run: <none, or the list>

Scope: <...>
Verdict: <PASS/FAIL> - <n> blockers, <n> major, <n> minor

<findings table, or top findings if long>

Commands run:
<verbatim output>
```

The findings list is meant to hand straight back to `5-build` as work: "level 3 concurrency gives two 201s; DELETE on a cancelled booking returns 404 instead of 409" is a task list, not just a verdict.
