# Firm Payments Service

Local development scaffold for the service described in
[requirements](docs/requirements.md) and [technology stack](docs/tech_stack.md).
Bulk payment processing is implemented against the platform-owned `firms` and
`payments` tables, with a service-owned audit table. Payment requests require bearer JWT authentication and payer authorization
by default; operational endpoints require the separate static API key. The API is published on localhost and PostgreSQL is accessible only
inside Docker Compose. Local authentication uses Dex, published on loopback port 5556.

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
make up
make sample
```

`make setup` uses managed Python, creates the host `.venv`, installs Git
pre-commit hooks, and copies `.env.example` to `.env` if it does not already exist.
Build and startup also
work without setup, using Compose's local defaults. The host environment is for
Git hooks, checks, and formatting; the application and tests run in containers.

- pgAdmin: <http://127.0.0.1:5050> (login `admin@example.com` / `local-development`)
- API documentation: <http://127.0.0.1:8000/docs>
- Liveness: <http://127.0.0.1:8000/health/live>
- Readiness (checks PostgreSQL): <http://127.0.0.1:8000/health/ready>
- Prometheus metrics: <http://127.0.0.1:8000/metrics>

```sh
curl --fail -H "X-API-Key: local-operational-key" http://127.0.0.1:8000/health/ready
```

Source changes reload the running application. Dependency or image changes need
`make build` followed by `make up`. JSON application and Uvicorn logs go to stdout.

## Local authentication

Compose starts Dex with two local users, both with password `password`:

| User | Authorized payer firm UUID |
| --- | --- |
| `payer@example.test` | `3f1c9a2e-7b4d-4c1e-9a55-2d8e6f0b7c41` |
| `other@example.test` | `8b2e4c71-0d3a-4f6e-b1c9-5a7d2e9f4c10` |

`make up` initializes local platform tables, seeds the PDF's three firms when
`firms` is empty, and applies service audit migrations before starting the API.
Existing firms, balances, payments, and audit records survive subsequent starts.

Run `make sample` to obtain a fresh Dex token and submit `local/payment.json`,
the PDF's three-payment worked example. The script prints the HTTP status and
response; the first run returns **201** with three payments and one audit row.
It runs in the app container, so a custom `APP_PORT` needs no script changes.
Repeated submissions transfer the money again; startup never sends payments.

In pgAdmin, open **Local development → Local Firm Payments** and enter the
PostgreSQL password (`local-development` by default). Inspect `public.firms`,
`public.payments`, and `firm_payments_service.firm_payments_audit`. After one
sample request on a fresh database, balances in cents are:

| Firm | Initial balance | Balance after sample |
| --- | ---: | ---: |
| Pinecrest CPA Group | 5000000 | 3674875 |
| Lopez Bookkeeping | 50000 | 170075 |
| Nair Tax Services | 200000 | 1405050 |

`PGADMIN_PORT`, `PGADMIN_DEFAULT_EMAIL`, and `PGADMIN_DEFAULT_PASSWORD` configure
pgAdmin. Login credentials initialize its configuration volume only once.
The preloaded connection uses the default database name and user; if you change
`POSTGRES_DB` or `POSTGRES_USER`, edit its connection properties in pgAdmin.
PostgreSQL remains accessible only inside Compose.

The script can also run on the host with Python 3:

```sh
python3 local/request-example.py --api-url http://localhost:8000
```

For other requests, obtain a token and submit your own JSON:

```sh
TOKEN=$(curl --fail --silent \
  -u firm-payments:local-payment-client-secret \
  --data-urlencode 'grant_type=password' \
  --data-urlencode 'username=payer@example.test' \
  --data-urlencode 'password=password' \
  --data-urlencode 'scope=openid federated:id' \
  http://localhost:5556/dex/token | python3 -c 'import json, sys; print(json.load(sys.stdin)["id_token"])')
curl --fail -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  --data @payment.json http://localhost:8000/api/v1/payments/bulk
```

Use the `id_token`; Dex's OAuth access token is opaque. Dex uses memory storage,
so restarting it invalidates previously issued tokens. Its password flow and
published credentials are for local development only.

Direct/deployed execution defaults to `AUTH_TOKEN_PROFILE=standard` (ES256 and
`payer_firm_uuid`), `AUTH_ENABLED=true`, and HTTPS JWKS URLs. Supply
`AUTH_ISSUER`, `AUTH_AUDIENCE`, and `AUTH_JWKS_URL`; incomplete enabled settings
prevent startup. `AUTH_JWKS_TIMEOUT_SECONDS` defaults to 30; keys are fetched
for every request without caching. Compose explicitly uses the `dex` profile
(RS256 and `federated_claims.user_id` from connector `local`) and
`AUTH_ALLOW_HTTP=true` for local networking. Keep HTTP permission disabled in
deployments and provide HTTPS ingress. `AUTH_ENABLED=false` explicitly skips
payment authentication and authorization; it does not disable operational keys.

## Development commands

| Command | Purpose |
| --- | --- |
| `make help` | List commands |
| `make setup` | Sync locked host dependencies and install Git hooks |
| `make build` | Build the development container |
| `make up` | Build and start services; initialize local data and wait for readiness |
| `make down` | Stop services, preserving the database volume |
| `make logs` | Follow service logs; Ctrl-C stops following |
| `make sample` | Submit the authenticated PDF payment example |
| `make test` | Start PostgreSQL and Dex and run pytest with coverage |
| `make check` | Run every pre-commit hook against all tracked files on the host |
| `make format` | Apply Ruff fixes and formatting on the host |
| `make migrate` | Apply Alembic migrations |
| `make migration MESSAGE="description"` | Generate a migration from metadata |

Tests cover health endpoints, PostgreSQL connectivity, readiness failures,
metrics, payment validation and processing, and JSON logging. Coverage prints
in the terminal. To run a subset:

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
to Codex for tests. Checks run on the host through `make check`; new files
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

Alembic is wired to the shared settings and SQLAlchemy metadata for
service-owned tables. Migrations create the `firm_payments_service` PostgreSQL
schema and move the audit table to `firm_payments_service.firm_payments_audit`,
preserving existing rows and grants. Compose applies migrations automatically before starting the app;
`make migrate` remains available for explicit migration execution. The migration role owns the schema; the runtime role needs USAGE
on it and only INSERT and SELECT on the audit table. Autogeneration is limited to
registered service tables; the existing Alembic version table stays in the default
schema. The platform owns `firms` and `payments`, so this service does not migrate
them. When adding service-owned models, register their tables in the metadata used by the migration
environment, generate a revision, review it, and apply it:

```sh
make migration MESSAGE="create audit table"
make migrate
```

`make down` preserves data. To deliberately erase **all local database data and pgAdmin settings** and
restore the PDF starting balances on the next `make up`:

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
