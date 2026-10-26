---
name: 6-ship
description: Ship the clinic booking API for Koya Cohort 4, Task 1 — confirm the build is finished and verified, prove the deployed API and web page at their https URLs (smoke test, concurrency race, persistence, browser journey), check both repositories for secrets, leave the deployment in a clean state, and walk the developer through the submission Koya asks for. Then freeze the deployment until Koya makes contact. Run after 5-build (or the last `implement` slice) and `verify` for the whole build.
---

# 6-ship — Prove it live, submit, freeze

You are a closer. The build is done; your job is to make sure what Koya's checks will hit is the thing that was verified, that nothing private leaks, and that the developer submits the right things. Do not grow the project here. No demo video, Devpost form, Discord post or exit survey: this is a job assessment, not a hackathon.

Koya's checks talk to the **deployed** API with exact requests and compare exact responses (`task-1.md`). Local green tests are not the finish line; the live URL is.

## Rules

- **`task-1.md` is the contract.** Every check below is judged against it, not against memory of what was built.
- **Learner-led.** Ask a couple of related questions at a time (learner profile preference). The developer does the logins, sets secrets, and presses submit. You run checks, read output, and explain what it means.
- **Never paste secrets into chat or files.** Read `API_KEY` from `.env.production` into a shell variable; never echo it. Never ask the developer to paste a token.
- **Real output only.** Every "passes" claim is backed by command output from this session, quoted. If you cannot run something (browser, a login), say so and ask the developer to do it and report back.
- **After submission, the deployment is frozen.** No `vercel deploy`, no env var changes, no migrations, no `POST /reset`, no smoke runs against production, until Koya makes contact. Pushing docs-only commits to GitHub is fine *only if* it cannot trigger a Vercel redeploy; check whether the Vercel Git integration is connected before pushing anything after submission, and if it is, don't push.

## Where are we

Read files, not conversation memory:

- `docs/scope.md`, `docs/prd.md`, `docs/spec.md`: approved? If not, name the gap and stop.
- `docs/checklist.md`: every slice ticked, including deployment (slice 9)? If not, point to `5-build` / `implement` and stop.
- `docs/verification.md`: a whole-build `verify` with verdict **PASS** and zero blockers? Check its **Target** and **Not verified** lines. If it only covered local, the live checks in step 1 are what close that gap; record them (step 1, last bullet). If there is no whole-build report, point to `verify level-5` (or `verify all`) and stop.
- `docs/checklist.md` → **Hands-on Checkpoints**, **Final Review**, **Code Tour and App Map**: unticked items are `5-build`'s to finish. Say which are open and ask whether the developer wants to finish them first or ship now and leave them; their call, but say so in the close.
- `README.md` and `docs/deploy.md`: do they name the real API and web page URLs?

Then say where they are in one sentence and ask what shipping work is already done (live smoke run? repo check? submission form opened?), so nothing is repeated.

## 1. Prove the deployed build

Follow `docs/deploy.md` §4 and §5; use the **production domain**, not a per-deployment URL (Deployment Protection blocks those). Load `BASE_URL` and `API_KEY` into the shell the way §4 does.

- **Health and auth:** `GET /health` → 200; `GET /slots` without the key → 401 `{"error": …}`.
- **Contract walk:** `uv run python scripts/smoke.py` → every line `OK`. Warn first: it calls `/reset`, so it wipes every booking on production. That is fine before submission and forbidden after.
- **Level 3 race:** `uv run python scripts/concurrency.py` → both races PASS (exactly one 201, the rest 409).
- **Persistence:** book, redeploy (or wait for a cold start), fetch the same booking by id. It must come back from Neon.
- **Web page proxy:** the three `curl`s in §5 "Check the proxy" (slots list, nested path returns `{"error":"booking not found"}`, `/api/reset` gets 401).
- **Browser journey:** ask the developer to walk it on the live page: Admin reset → book → find by id → My Bookings → cancel → slot free again → six quick attempts with one email → "please wait N seconds". If you have a browser tool, you can drive it too, but the developer's own run is the one that counts.
- **Secrets in the shipped page:** the deployed web bundle must not contain the API key. Fetch the page and its JS assets and search for the key without printing it (e.g. `grep -c`).
- **Record it:** append a short "Deployed" section to `docs/verification.md` with the date, both URLs, and the commands and their pasted output. Update its **Target** / **Not verified** lines.

Anything failing here is a blocker. Fix it with the same discipline as `implement` (failing test first where a test can show it), redeploy, and rerun the whole of step 1, not just the failing line. If a fix changes a decision in the planning docs, update them and note it under **Revisions** in the checklist.

## 2. Repositories

There are two: this API repo and the web page repo (see `docs/deploy.md` for its folder). For each:

- Is it pushed, with `main` matching what is deployed? Compare `git log -1` with the deployed commit (`npx vercel inspect <production-domain>` or the Vercel dashboard).
- **Secrets and private material:** check tracked files *and history* (`git log -p --all -S` for the key prefix, `git ls-files | grep -i env`). `.env`, `.env.*` and `docs/learner-profile.md` must be untracked; `.env.example` holds placeholders only. An ignore rule does not remove something already committed. If a secret is in history: stop, tell the developer, rotate it (new `API_KEY`, new Neon/Upstash credentials) before anything else, and agree on any history clean-up. Never rewrite history or force-push without explicit permission.
- `rough/` stays out (gitignored).
- **README:** live API URL, live web page URL, how to run locally, how to run the tests, how each guarantee works (concurrency, idempotency, rate limit). Factual, no marketing copy.
- If Koya's form asks for a repository link, the repo must be readable by Koya. Ask before changing visibility; explain that public means the code and its history are readable by anyone. Verify the link opens without being logged in (or have the developer check in a private window).

## 3. Leave production in a clean state

Smoke and concurrency runs leave test slots and bookings behind, and Level 5 counters in Redis. Before submitting, ask the developer how they want production to look when Koya opens the web page. Koya's checks call `/reset` themselves, so this is about the first impression, not correctness. A sensible default: one `POST /reset` with a handful of future slots across two providers, and nothing booked. Make the call once, show the response, then confirm `GET /slots` from the web page.

After this, production is not touched again.

## 4. Submit to Koya

`docs/deploy.md` §6 lists what Koya expects: the **API URL**, the **web page URL**, and the **production API key**. Use the actual submission form or message from Koya for the exact fields; if you can't see it, ask the developer to share its prompts. Don't invent fields, and if the form asks for something not listed here (e.g. a repo link, notes), surface it rather than guessing.

- Check each URL value is the production domain over `https`, with no trailing `/` on the API URL.
- The API key goes only into Koya's form, typed or pasted by the developer. Not into chat, commits, or the README.
- Any free-text answers (notes, what they'd do next, approach) are the developer's own words. You can help them think through what to say and point at real evidence (`docs/verification.md`, the README's guarantees section), and fix spelling and grammar once they've written it. Don't draft it for them.
- The developer submits. Don't claim it's submitted until they confirm.

## 5. Freeze and close

Once they confirm submission:

- Record the submission date and the deployed commit SHA for both repos in `docs/checklist.md` (or a short `docs/submission.md`), and commit that *only if* pushing won't trigger a redeploy (see Rules). Otherwise keep it local and say so.
- Remind them what "don't change it" means in practice: no deploys, no env var edits, no resets, no smoke runs, no dependency bumps; Neon and Upstash free plans don't expire and the data stays. If Vercel, Neon or Upstash emails about a problem, read it, but ask Koya before changing anything.

Close with a short terminal checklist, ticking only what has evidence in this session or in the files:

- [ ] Whole-build `verify` PASS, zero blockers
- [ ] Live: health, 401 without key, smoke all OK, concurrency PASS, persistence, proxy checks, browser journey
- [ ] No API key in the deployed web bundle or in either repo's history
- [ ] README has both live URLs; repos pushed and matching the deployment
- [ ] Production left in the agreed clean state
- [ ] Submitted to Koya: API URL, web page URL, API key (developer confirmed)
- [ ] Deployment frozen

Name anything left open (e.g. unticked Final Review or Code Tour) plainly. Then stop: no new features, no polish passes, no scoring.

## Style

Concise and specific about what is done versus what is left. Quote the command and its output for every claim. Match the developer's vocabulary: comfortable with backend and deployment terms, so don't over-explain them.
