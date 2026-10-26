# ================================
# STAGE 1: builder
# Install production dependencies from pyproject.toml/uv.lock
# ================================
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

WORKDIR /app

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --group prod

# Copy application source after dependency installation for better layer caching.
COPY . .


# ================================
# STAGE 2: runner
# ================================
FROM python:3.12-slim-bookworm AS runner

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

COPY --from=builder /app /app

RUN chmod +x ./scripts/runner.sh \
    && useradd --create-home --uid 1000 app \
    && chown -R app:app /app
USER app

EXPOSE 8000

CMD ["./scripts/runner.sh"]
