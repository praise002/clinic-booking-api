# Deploying for free: Vercel + Neon + Upstash

Everything here is on a free plan.

| Piece | Where | Free allowance |
|---|---|---|
| API (FastAPI) | **Vercel**, project `clinic-booking-api` | Hobby plan; the app runs as one Python function |
| Web page | **Vercel**, project `clinic-booking-frontend` | Hobby plan |
| Postgres | **Neon** | 0.5 GB storage, 100 compute-hours a month, never expires; sleeps after 5 min idle, wakes on the next query |
| Redis (rate limit) | **Upstash** | 500,000 commands a month, 256 MB |

Put all three in the **same region, US East**: Vercel `iad1` (set in `vercel.json`), Neon **AWS US East 1 (N. Virginia)**, Upstash **us-east-1**. Every request crosses between them, so distance adds up.

`API` = `~/Documents/Freelance projects/koya-assessment/clinic-booking-api`, `WEB` = `…/clinic-booking-frontend`.

---

## 0. Your secrets file

All the connection strings go in **`API/.env.production`**. It's gitignored and listed in `.vercelignore`, so it never reaches GitHub or Vercel uploads. It already holds the production `API_KEY`. By the end it will have:

```bash
API_KEY=...                 # already there
DATABASE_URL=...            # Neon, POOLED   (step 1)
DATABASE_URL_DIRECT=...     # Neon, DIRECT   (step 1)
REDIS_URL=...               # Upstash, rediss://   (step 2)
```

Open it in your editor and paste values in as you go.

## 1. Neon (Postgres)

1. Go to **neon.com** → **Sign up**. GitHub or Google works.
2. **Create project**:
   - Name: `clinic-booking`
   - Postgres version: **17**
   - Region: **AWS US East 1 (N. Virginia)**
3. On the project dashboard, press **Connect**:
   - Database `neondb`, role `neondb_owner`.
   - With **Connection pooling ON**, copy the string. Its host contains `-pooler`. Paste it as `DATABASE_URL=` in `.env.production`.
   - Turn **Connection pooling OFF** and copy again. Paste it as `DATABASE_URL_DIRECT=`.

   Both look like `postgresql://neondb_owner:…@ep-…[-pooler].us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require`. Paste them **as they are**: the app translates `sslmode` and handles the pooler itself (`src/db_options.py`).
4. **Create the tables** (once), from **API**:

   ```bash
   DATABASE_URL="$(grep ^DATABASE_URL_DIRECT .env.production | cut -d= -f2-)" uv run alembic upgrade head
   ```

   You should see `Running upgrade -> 0001` and `0001 -> 0002`. Migrations use the **direct** URL; the app uses the **pooled** one.

## 2. Upstash (Redis)

1. Go to **upstash.com** → **Sign up** (GitHub or Google).
2. **Redis** → **Create database**:
   - Name: `clinic-booking`
   - Region: **AWS us-east-1**. If asked for a primary region, pick that, with no read regions.
   - Plan: **Free**
3. On the database page, under **Connect**, choose the **TCP / redis-cli** tab (not REST). Copy the URL that starts with **`rediss://`** (two s's, meaning TLS): `rediss://default:<password>@<name>.upstash.io:6379`.
4. Paste it as `REDIS_URL=` in `.env.production`.

## 3. Deploy the API to Vercel

From **API**:

```bash
npx vercel login                                   # opens the browser
npx vercel link                                    # "Set up a new project?" yes → name: clinic-booking-api
```

Add the environment variables, each for **Production**:

```bash
# printf '%s' "$(…)" passes the value without a trailing newline (the API compares the key exactly).
for name in API_KEY DATABASE_URL REDIS_URL; do
  printf '%s' "$(grep "^$name=" .env.production | cut -d= -f2-)" | npx vercel env add $name production
done
printf '5'   | npx vercel env add DB_POOL_SIZE production
printf '15'  | npx vercel env add DB_MAX_OVERFLOW production
printf '1.0' | npx vercel env add REDIS_TIMEOUT_SECONDS production
```

- `DATABASE_URL` must be the **pooled** Neon URL.
- The pool settings are smaller because each Vercel instance has its own pool.
- The Redis timeout is 1 second rather than 0.5, to leave room for TLS to Upstash.

Deploy:

```bash
npx vercel deploy --prod                           # prints https://clinic-booking-api-<…>.vercel.app
```

Vercel finds the app through `[tool.vercel] entrypoint = "src.main:app"` in `pyproject.toml`, and installs the dependencies from `uv.lock`. `.vercelignore` keeps tests, docs, migrations and every `.env` file out of the upload.

## 4. Prove the live API

From **API**, with the URL from step 3:

```bash
export BASE_URL=https://clinic-booking-api-<…>.vercel.app
export API_KEY=$(grep ^API_KEY .env.production | cut -d= -f2-)

curl -s $BASE_URL/health                                    # {"status":"ok"}
curl -s -o /dev/null -w "%{http_code}\n" $BASE_URL/slots    # 401 without the key
uv run python scripts/smoke.py                              # every line OK
uv run python scripts/concurrency.py                        # both races PASS
```

**Persistence:** book once, redeploy, and fetch it again:

```bash
curl -s -X POST $BASE_URL/reset -H "X-API-Key: $API_KEY" -H 'Content-Type: application/json' \
  -d '{"slots":[{"id":"s1","provider":"Dr Ade","start":"2030-01-01T09:00:00Z","end":"2030-01-01T09:30:00Z"}]}'
ID=$(curl -s -X POST $BASE_URL/bookings -H "X-API-Key: $API_KEY" -H 'Content-Type: application/json' \
  -d '{"slot_id":"s1","name":"Ada Obi","email":"ada@example.com"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["id"])')
npx vercel deploy --prod                                    # a fresh deployment
curl -s $BASE_URL/bookings/$ID -H "X-API-Key: $API_KEY"     # same booking: it lives in Neon
```

`$BASE_URL/docs` in a browser: it loads, and **Authorize** takes the key.

The first request after a few quiet minutes takes about 1–2 s while the function and Neon wake up. After that, requests are fast.

## 5. Deploy the web page

From **WEB**:

```bash
npx vercel link                                     # new project → clinic-booking-frontend
printf 'https://clinic-booking-api-<…>.vercel.app' | npx vercel env add API_BASE_URL production
printf '%s' "$(grep ^API_KEY= ../clinic-booking-api/.env.production | cut -d= -f2-)" | npx vercel env add API_KEY production
npx vercel deploy --prod                            # prints https://clinic-booking-frontend-<…>.vercel.app
```

`API_BASE_URL` has no trailing `/`.

### Check the proxy

```bash
export WEB=https://clinic-booking-frontend-<…>.vercel.app
curl -s $WEB/api/slots                                                   # the API's slot list
curl -s $WEB/api/bookings/00000000-0000-4000-8000-000000000000           # {"error":"booking not found"} = nested paths reach the API
curl -s -X POST $WEB/api/reset -H 'Content-Type: application/json' -d '{"slots":[]}'   # 401: reset never gets the server key
```

If the nested path returns Vercel's own 404 page instead of `{"error":"booking not found"}`, the catch-all function isn't matching nested paths. Tell me, and I'll switch to the fallback: one `api/proxy.js` plus a rewrite in `vercel.json`.

Then walk the journey in the browser: Admin reset with the key → book → find by id → My Bookings → cancel → slot free again → six quick attempts with one email → "please wait N seconds".

## 6. Finish

1. Put both URLs into `API/README.md` and `WEB/README.md` (replace `<API_URL>` / `<WEB_URL>`), commit, and push.
2. Submit to Koya: the **API URL**, the **web page URL**, and the **production API key**.
3. **After submitting, change nothing** until Koya makes contact (CLAUDE.md): no `vercel deploy`, no env var changes. Neon and Upstash free plans don't expire, and the data stays.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Deploy fails "no FastAPI app found" | Entrypoint not read | Check `[tool.vercel] entrypoint = "src.main:app"` is in `pyproject.toml` |
| `500` on every request; logs mention `DATABASE_URL` or `API_KEY` | An env var is missing | `npx vercel env ls`, add it, `npx vercel deploy --prod` |
| `500`; logs: `relation "slots" does not exist` | Migrations not run | Step 1.4 |
| `500`; logs: `prepared statement … already exists` | Pooled URL without `-pooler` in the host | Use Neon's pooled string exactly as copied |
| Every request `401` | `API_KEY` has quotes, spaces or a newline | Remove it (`npx vercel env rm API_KEY production`) and add it again with the `printf '%s' "$(…)"` pipe above |
| Logs warn `rate limit skipped, Redis unavailable` | `REDIS_URL` wrong (`redis://` instead of `rediss://`, or the REST URL) | Use the TCP `rediss://` URL; bookings keep working meanwhile (fail open) |
| 429s right away during checks | One email used more than 5 times a minute | Expected (Level 5); `POST /reset` clears the counts |
| Page: "Couldn't reach the booking service" | `API_BASE_URL` wrong | Fix it in the web project's env vars, then `npx vercel deploy --prod` |
