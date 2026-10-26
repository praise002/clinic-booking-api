import { defineRailway, github, group, postgres, preserve, project, redis, service } from "railway/iac";

// The clinic booking API on Railway: the API service, Postgres (bookings, slots,
// idempotency records) and Redis (per-email rate-limit counters).
// Apply with `railway config plan` then `railway config apply` from this folder.
export default defineRailway(() => {
    const db = postgres("Postgres");
    const cache = redis("Redis");

    const api = service("api", {
        source: github("praise002/clinic-booking-api", { branch: "main" }),
        build: { builder: "DOCKERFILE", dockerfilePath: "Dockerfile" },
        // Migrations run once in preDeploy; the start command skips them.
        preDeploy: "alembic upgrade head",
        start: "./scripts/runner.sh --skip-migrations",
        healthcheck: "/health",
        healthcheckTimeout: 120,
        replicas: 1,
        deploy: { restartPolicyType: "ON_FAILURE", restartPolicyMaxRetries: 5 },
        env: {
            // The value lives in Railway only; set it with `railway variables`.
            API_KEY: preserve(),
            // postgresql:// from Railway; src/config.py switches it to the asyncpg driver.
            DATABASE_URL: db.env.DATABASE_URL,
            REDIS_URL: cache.env.REDIS_URL,
            // Two worker processes: everything shared lives in Postgres or Redis.
            WEB_CONCURRENCY: "2",
        },
    });

    return project("clinic-booking-api", {
        resources: [api, group("Infrastructure", [db, cache])],
    });
});
