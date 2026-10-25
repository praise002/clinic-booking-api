# Clinic booking API (Koya Cohort 4 assessment, Task 1)

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
