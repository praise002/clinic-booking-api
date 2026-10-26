.PHONY: up_build up up_d down show_logs install lock mmig mig tests lint lint-fix format format-check check smoke

ifneq (,$(wildcard ./.env))
include .env
export
endif

up_build:
	docker compose up --build

up:
	docker compose up

up_d:
	docker compose up -d

down:
	docker compose down

show_logs:
	docker compose logs

# ── Dependency management (uv) ──────────────────────────────────────────────

install:
	uv sync --all-groups

lock:
	uv lock

# ── Database ────────────────────────────────────────────────────────────────

mmig:
	if [ -z "$(message)" ]; then \
		docker compose exec api alembic revision; \
	else \
		docker compose exec api alembic revision -m "$(message)"; \
	fi

mig:
	docker compose exec api alembic upgrade head

# ── Tests and checks ────────────────────────────────────────────────────────

# Runs on the host against the compose db (TEST_DATABASE_URL), so `make up_d` first.
tests:
	uv run pytest

smoke:
	BASE_URL=$${BASE_URL:-http://localhost:8070} uv run python scripts/smoke.py

lint:
	uv run ruff check

lint-fix:
	uv run ruff check --fix

format:
	uv run ruff format

format-check:
	uv run ruff format --check

check: lint format-check
