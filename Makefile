COMPOSE := docker compose
UV ?= uv
PYTEST_ARGS ?=

.PHONY: help setup build up down logs test check format migrate migration

help:
	@echo 'setup     Install host dependencies and Git hooks'
	@echo 'build     Build the development image'
	@echo 'up        Build and start the app and PostgreSQL'
	@echo 'down      Stop services (preserve database data)'
	@echo 'logs      Follow service logs'
	@echo 'test      Run all tests with PostgreSQL and coverage (PYTEST_ARGS optional)'
	@echo 'check     Run all pre-commit checks'
	@echo 'format    Fix lint issues and format Python files'
	@echo 'migrate   Apply database migrations'
	@echo 'migration MESSAGE="..."  Generate a migration'

setup:
	$(UV) sync --locked --managed-python
	@test -f .env || cp .env.example .env
	$(UV) run --locked pre-commit install

build:
	$(COMPOSE) build

up:
	$(COMPOSE) up --build --wait

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs --follow

test:
	$(COMPOSE) up --wait db
	$(COMPOSE) run --build --rm -T app uv run --locked python -m pytest $(PYTEST_ARGS)

check:
	$(UV) run --locked pre-commit run --all-files --show-diff-on-failure

format:
	$(UV) run --locked ruff check --fix .
	$(UV) run --locked ruff format .

migrate:
	$(COMPOSE) up --wait db
	$(COMPOSE) run --build --rm -T app uv run --locked alembic upgrade head

migration:
	@test -n "$(MESSAGE)" || (echo 'Usage: make migration MESSAGE="description"' >&2; exit 1)
	$(COMPOSE) up --wait db
	$(COMPOSE) run --build --rm -T app uv run --locked alembic revision --autogenerate -m "$(MESSAGE)"
