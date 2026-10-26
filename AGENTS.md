# Clinic booking API (Koya Cohort 4 assessment, Task 1)

Instructions for coding agents (Codex, Cursor, Gemini CLI and others that read `AGENTS.md`). Claude Code reads the same rules from `CLAUDE.md`. Keep the two files in step.

## Skills

The project's skills are in [`.agents/skills/`](.agents/skills), one folder per skill, each with a `SKILL.md`: frontmatter `name` and `description`, then the instructions. Some also have `templates/` or `references/`. When the user names a skill (`5-build`, "run verify level-3", "implement slice 4"), read that `SKILL.md` and follow it. Read its templates and references only when the skill says to.

| Skill | Use it for |
|---|---|
| `1-start` → `2-scope` → `3-prd` → `4-spec` | The planning docs in `docs/` (all approved) |
| `5-build` | Plan the slices into `docs/checklist.md`, or resume the build at the first unchecked slice |
| `implement` | One slice at a time, test first |
| `verify` | Check a Koya level (or everything) against `task-1.md`; writes `docs/verification.md` |
| `6-ship` | Final checks and submission |

`.agents/skills/` is a copy of `.claude/skills/` (Claude Code's location); edit both, or edit one and copy it over:

```bash
rsync -a --delete .claude/skills/ .agents/skills/
```

## Workflow

Spec-driven, learner-led. The developer wants to understand what is being built, not just get code.

1. `1-start` → `2-scope` → `3-prd` → `4-spec`: planning docs in `docs/`.
2. `5-build` plans the slices into `docs/checklist.md`; then either `5-build` drives the build, or `implement` does one slice at a time, test-first.
3. `verify level-N` after each Koya level, before starting the next.
4. `6-ship` for the final checks and submission.

## These rules override the learn-ai-basics skills

The `1-start` … `6-ship` skills were written for a Devpost hackathon. Where they conflict with this project, this file wins:

- **The contract is fixed.** `task-1.md` is the normative spec (endpoints, status codes, bodies, headers). Scope and PRD interviews should not re-decide it; focus them on what it leaves open (stack, web page look and flow, how far through the 5 levels to go, design of concurrency/idempotency/rate limiting).
- **Deployment is required**, at an https URL, with persistent storage. It is not optional.
- **No demo video, Devpost form, Discord post, or exit survey.** In `6-ship`, replace those with: the deployed API and web page URLs, a smoke test passing against the deployed URL, and the submission Koya asks for.
- **No 2-4 hour cap.** Size the work to the five levels: do each level properly before moving on.
- **After submission, don't change the deployment** until Koya makes contact.
- Every error body is `{"error": "<message>"}`; every request needs `X-API-Key`.

## Project conventions

- **Commits:** no `Co-Authored-By` or other AI-attribution lines.
- **Every endpoint is fully documented** in OpenAPI (summary, description, every response status with an example); `tests/test_openapi_docs.py` enforces it.
- **Run before claiming done:** `make tests` (needs `make up_d`: Postgres on 5452, Redis on 6396), `uv run ruff check`, `make smoke`, and `scripts/concurrency.py`. Paste real output; don't infer a pass.
- **Hosting:** Vercel (API and web page) + Neon (Postgres) + Upstash (Redis); see `docs/deploy.md`.
