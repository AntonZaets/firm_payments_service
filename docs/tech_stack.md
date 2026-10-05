# Project technology stack

## general

- language: python 3.14
- package manager: uv
- framework: FastAPI
- runtime: Uvicorn
- db: postgresql + SQLAlchemy + Alembic + Psycopg 3
- db migrations: Alembic
- configuration: pydantic-settings
- logging: python-json-logger
- monitoring: prometheus-client
- containerization: docker-compatible

## development

- testing: pytest, pytest-cov, Polyfactory for test data factories
- linting: ruff, pyright
- other dev tools: pre-commit, bandit, deptry
- deployment: docker compose, Makefile

## CI
- GitHub Actions
