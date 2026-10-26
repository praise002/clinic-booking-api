# Deploying: Railway (API) + Vercel (web page)

A step-by-step guide. Run the commands from the folder named at the top of each step. `API` means `~/Documents/Freelance projects/koya-assessment/clinic-booking-api`, `WEB` means `…/clinic-booking-frontend`.

**What you'll end up with**

- The API at `https://<something>.up.railway.app`, with Postgres and Redis on Railway.
- The web page at `https://<something>.vercel.app`, whose `/api/*` function forwards to the API with the key.

**The production API key** is already generated in `API/.env.production` (gitignored). It's different from your dev key. You'll paste it into Railway, Vercel and the Koya submission. Read it with:

```bash
grep ^API_KEY .env.production
```

---

## 1. Push the API to GitHub

Railway builds the API from `github.com/praise002/clinic-booking-api` (branch `main`).

From **API** (or VS Code → Source Control → Sync/Push):

```bash
git push origin main
```

Check that the repo on GitHub shows the latest commit, "Prepare for production on Railway".

## 2. Create the Railway project

The project is defined in `API/.railway/railway.ts`: Postgres, Redis, and the `api` service.

From **API**:

```bash
npx @railway/cli login               # opens the browser
npx @railway/cli init                # create a new project, name it clinic-booking-api
cd .railway && npm install && cd ..  # the railway/iac package (already installed once)
npx @railway/cli config plan         # READ the plan: 1 service (api), Postgres, Redis
npx @railway/cli config apply        # create them
```

> If `config plan`/`apply` isn't available in your CLI version, use the dashboard instead (**2b**).

### 2b. Dashboard fallback (same result)

1. railway.com → **New Project** → **Deploy from GitHub repo** → `praise002/clinic-booking-api`. Name the service `api`.
2. In the project: **+ New → Database → PostgreSQL**, then **+ New → Database → Redis**.
3. `api` service → **Settings**:
   - Builder: **Dockerfile** (path `Dockerfile`).
   - **Pre-deploy command:** `alembic upgrade head`
   - **Custom start command:** `./scripts/runner.sh --skip-migrations`
   - **Healthcheck path:** `/health`
   - Restart policy: On failure.
4. `api` service → **Variables**:
   - `DATABASE_URL` = `${{Postgres.DATABASE_URL}}`
   - `REDIS_URL` = `${{Redis.REDIS_URL}}`
   - `WEB_CONCURRENCY` = `2`

## 3. Set the API key and get the URL

From **API**:

```bash
npx @railway/cli link                                   # pick the project, if not linked
npx @railway/cli variables --service api --set "API_KEY=$(grep ^API_KEY .env.production | cut -d= -f2)"
npx @railway/cli domain --service api                   # prints https://<something>.up.railway.app
```

(Dashboard: `api` → Variables → `API_KEY`; `api` → Settings → Networking → **Generate Domain**.)

Wait for the deploy to finish (dashboard shows **Active**; the logs show "Running upgrade -> 0001" then "-> 0002", and gunicorn booting 2 workers).

## 4. Prove the live API

From **API**, with your Railway URL:

```bash
export BASE_URL=https://<something>.up.railway.app
export API_KEY=$(grep ^API_KEY .env.production | cut -d= -f2)

curl -s $BASE_URL/health                               # {"status":"ok"}
curl -s -o /dev/null -w "%{http_code}\n" $BASE_URL/slots   # 401 without the key
uv run python scripts/smoke.py                         # every line OK
uv run python scripts/concurrency.py                   # both races PASS
```

**Persistence:** book once, restart, and fetch it again:

```bash
curl -s -X POST $BASE_URL/reset -H "X-API-Key: $API_KEY" -H 'Content-Type: application/json' \
  -d '{"slots":[{"id":"s1","provider":"Dr Ade","start":"2030-01-01T09:00:00Z","end":"2030-01-01T09:30:00Z"}]}'
ID=$(curl -s -X POST $BASE_URL/bookings -H "X-API-Key: $API_KEY" -H 'Content-Type: application/json' \
  -d '{"slot_id":"s1","name":"Ada Obi","email":"ada@example.com"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["id"])')
npx @railway/cli redeploy --service api -y             # or dashboard → Redeploy
curl -s $BASE_URL/bookings/$ID -H "X-API-Key: $API_KEY"   # same booking after the redeploy
```

Then `$BASE_URL/docs` in a browser: it loads, **Authorize** takes the key.

## 5. Deploy the web page to Vercel

From **WEB**:

```bash
npx vercel login
npx vercel link                       # create a new project (framework: Vite is detected)
npx vercel env add API_BASE_URL production    # paste https://<something>.up.railway.app (no trailing /)
npx vercel env add API_KEY production         # paste the production key
npx vercel deploy --prod              # prints https://<something>.vercel.app
```

(Dashboard alternative: vercel.com → Add New → Project needs a Git repo; the CLI deploys straight from the folder.)

### Check the proxy on the live page

```bash
export WEB=https://<something>.vercel.app
curl -s $WEB/api/slots                                        # the API's slot list (key added by the function)
curl -s -o /dev/null -w "%{http_code}\n" $WEB/api/bookings/00000000-0000-4000-8000-000000000000   # 404 = nested paths reach the API
curl -s -X POST $WEB/api/reset -H 'Content-Type: application/json' -d '{"slots":[]}'   # 401: reset never gets the server key
```

If the nested path (`/api/bookings/<id>`) returns Vercel's own 404 page instead of `{"error":"booking not found"}`, the catch-all function isn't matching nested paths. Tell me and I'll switch to the fallback from the spec: a single `api/proxy.js` plus a `vercel.json` rewrite.

Then open the page and walk the journey: Admin reset with the key → book → find by id → My Bookings → cancel → slot free again → six quick attempts with one email → "please wait N seconds".

## 6. Finish

1. Put both URLs into `API/README.md` and `WEB/README.md` (replace `<RAILWAY_URL>` and `<VERCEL_URL>`), commit, push the API (Railway redeploys automatically; that's fine *before* submitting).
2. Submit to Koya: the API URL, the web page URL, and the production API key.
3. **After submitting, don't push, redeploy or change variables** until Koya makes contact (CLAUDE.md). Railway auto-deploys on every push to `main`, so don't push the API repo either.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Deploy fails at pre-deploy | Migration couldn't reach Postgres | Check `DATABASE_URL` references `Postgres.DATABASE_URL`; the app converts `postgresql://` to asyncpg itself |
| Healthcheck fails | App not listening on Railway's `PORT` | `runner.sh` binds `$PORT`; make sure the start command is `./scripts/runner.sh --skip-migrations` |
| Every request 401 | `API_KEY` missing or has quotes/spaces | Re-set it with `railway variables --set` |
| 429s right away during checks | Same email used more than 5 times a minute | Expected (Level 5); `POST /reset` clears the counts |
| Page shows "Couldn't reach the booking service" | `API_BASE_URL` wrong or has a trailing `/path` | Fix it with `vercel env rm/add`, then `vercel deploy --prod` |
| Logs warn "rate limit skipped, Redis unavailable" | `REDIS_URL` not set | Reference `Redis.REDIS_URL`; bookings still work meanwhile (fail-open) |
