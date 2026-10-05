# Firm Payments Service

Local development scaffold for the service described in
[requirements](docs/requirements.md) and [technology stack](docs/tech_stack.md).
Payment processing, platform tables, and application authorization are not
implemented yet. Only operational endpoints exist; the API is published on
localhost and PostgreSQL is accessible only inside Docker Compose.

## Prerequisites

- Docker with Compose v2 or newer and a running daemon.
- GNU Make and Git.
- uv 0.12.23 or newer. If your installation supports it, upgrade with
  `uv self update`; for pipx installations use `pipx upgrade uv`.
  Otherwise upgrade using the method that installed uv.
- uv downloads managed Python 3.14.8 for host Git hooks during setup.

Containers use Python 3.14.8, PostgreSQL 18.6, and uv 0.12.23. Python runtime
and development dependencies are pinned in `pyproject.toml` and `uv.lock`.

## First run

```sh
make setup
make build
make migrate
make up
```

`make setup` uses managed Python, creates the host `.venv`, installs Git
pre-commit hooks, and copies `.env.example` to `.env` if it does not already exist.
Build and startup also
work without setup, using Compose's local defaults. The host environment is for
Git hooks; the application, checks, and tests run in containers.

- API documentation: <http://127.0.0.1:8000/docs>
- Liveness: <http://127.0.0.1:8000/health/live>
- Readiness (checks PostgreSQL): <http://127.0.0.1:8000/health/ready>
- Prometheus metrics: <http://127.0.0.1:8000/metrics>

```sh
curl --fail -H "X-API-Key: local-operational-key" http://127.0.0.1:8000/health/ready
```

Source changes reload the running application. Dependency or image changes need
`make build` followed by `make up`. JSON application and Uvicorn logs go to stdout.

## Development commands

| Command | Purpose |
| --- | --- |
| `make help` | List commands |
| `make setup` | Sync locked host dependencies and install Git hooks |
| `make build` | Build the development container |
| `make up` | Build and start services; wait for readiness |
| `make down` | Stop services, preserving the database volume |
| `make logs` | Follow service logs; Ctrl-C stops following |
| `make test` | Start PostgreSQL and run pytest with coverage |
| `make check` | Run every pre-commit hook against all tracked files |
| `make format` | Apply Ruff fixes and formatting |
| `make migrate` | Apply Alembic migrations |
| `make migration MESSAGE="description"` | Generate a migration from metadata |

Tests cover health endpoints, PostgreSQL connectivity, readiness failures,
metrics, and JSON logging. Coverage prints in the terminal. To run a subset:

```sh
docker compose run --rm app uv run --locked python -m pytest tests/unit
```

Pre-commit runs Ruff lint/format, strict Pyright, Bandit, dependency checks, and
checks for whitespace, file endings, YAML/TOML syntax, merge conflicts, private
keys, and large files. New files must be added to Git for pre-commit to inspect
them. Host hooks use the same locked dependencies as the container.

### Codex hooks

The repo's `.codex/hooks.json` runs `make check` after `apply_patch` edits and
before Codex finishes each turn (`Stop`), covering shell-based edits at turn end.
A separate `Stop` hook also runs `make test`.
Checks run synchronously; failures return feedback so Codex can fix them and
rerun checks. Ruff and whitespace hooks can modify files themselves.

Restart Codex after installing this configuration, trust the project, and use
`/hooks` to review and trust the repo hooks. Docker must be running and accessible
to Codex. These checks use the same container workflow as `make check`; new files
still need to be added to Git to be included. Read-only turns also run the final
check.

GitHub Actions builds the image, runs checks and tests, applies migrations twice,
and smoke-tests the running application on pushes and pull requests.

## Configuration and database

Edit `.env` using `.env.example` as a reference. `DATABASE_URL` must use the
`postgresql+psycopg://` scheme. For container commands its hostname is `db`.
`LOG_LEVEL` accepts DEBUG, INFO, WARNING, ERROR, or CRITICAL. Compose enables
reload. `APP_PORT` defaults to 8000; change it in `.env` if that port is occupied.
Use the configured port in the URLs above. Operational endpoints require the
`X-API-Key` header matching `OPERATIONAL_API_KEY`. Compose supplies a local-only
default; deployments must inject a secret key and restrict access to private
networking. Direct execution requires a nonempty key in configuration. Direct execution with
`uv run python -m firm_payments_service`
defaults to reload disabled and requires a reachable PostgreSQL URL.

The supplied database credentials are for local development only. If changing
them, update both the `POSTGRES_*` variables and `DATABASE_URL`. PostgreSQL uses
the initialization credentials only when its data volume is empty; changing
`.env` does not change an existing database user's password.

Alembic is wired to the shared settings and empty SQLAlchemy metadata. No firms
or payments tables are created yet. When adding models, register their tables in
the metadata used by the migration environment, generate a revision, review it,
and apply it:

```sh
make migration MESSAGE="create platform tables"
make migrate
```

`make down` preserves data. To deliberately erase **all local database data**:

```sh
docker compose down --volumes
```

## Updating dependencies

Check PyPI for the newest stable, non-yanked versions, update the exact pins in
`pyproject.toml`, then:

```sh
uv lock --upgrade
make setup
make build
make check
make test
make up
```

Keep Python on the 3.14 series. Update pinned Python, PostgreSQL, and uv image
versions explicitly. Commit both the manifest and lockfile. Installs use
`--locked`, so stale lockfiles fail instead of changing dependencies silently.

## Troubleshooting

- Docker permission or connection errors: ensure the daemon is running and your
  user can run `docker info`.
- uv version error: upgrade host uv to at least 0.12.23 before `make setup`.
- Port 8000 in use: set `APP_PORT=18000` in `.env`, then run `make up`.
- Readiness fails: inspect `make logs` and check the database URL and credentials.
  Readiness returns HTTP 503 without exposing connection details.
- First build or hook run requires network access to package and image registries
  and the pinned standard pre-commit hook repository.
- Dependency changes: rebuild the image; the container virtual environment is
  separate from the host `.venv`.
