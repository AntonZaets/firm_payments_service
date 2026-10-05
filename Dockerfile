FROM ghcr.io/astral-sh/uv:0.12.23 AS uv
FROM python:3.14.8-slim

COPY --from=uv /uv /uvx /usr/local/bin/
ENV UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --locked
COPY firm_payments_service ./firm_payments_service
COPY tests ./tests
COPY local ./local
COPY db_migrations ./db_migrations
COPY alembic.ini ./
CMD ["uv", "run", "--locked", "python", "-m", "firm_payments_service"]
