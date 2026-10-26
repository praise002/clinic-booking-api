#!/bin/bash

set -e  # exit immediately if any command fails

RUN_PORT="${PORT:-8000}"
WEB_WORKERS="${WEB_CONCURRENCY:-2}"

# Railway runs migrations in preDeploy and passes --skip-migrations.
if [ "${1:-}" != "--skip-migrations" ]; then
    echo "Running Alembic migrations..."
    alembic upgrade head
fi

# Two workers on purpose: anything shared between requests must live in Postgres or Redis.
# Extra flags (e.g. --reload in compose) come from GUNICORN_CMD_ARGS.
echo "Starting FastAPI server..."
exec gunicorn src.main:app \
    --workers "$WEB_WORKERS" \
    --worker-class uvicorn.workers.UvicornWorker \
    --timeout 30 \
    --bind "[::]:$RUN_PORT"
