# Architecture

Status: core architecture, module hierarchy, and transaction strategy confirmed.

## Overview

This document defines the service's structure and responsibilities, payment
transaction flow, concurrency handling, and execution model.

## Structure and responsibilities

- Use one FastAPI application with the bulk-payment endpoint defined in [API](api.md).
- Keep request schemas and validation at the API boundary. Validate nonempty payment lists and prohibit self-payments in request schemas before calling the payment service.
- Register a FastAPI validation exception handler so framework and service validation share the [API error format](api.md#validation-error-response).
- The payment service owns transfer rules and scopes each attempt with `make_session`. This context manager accepts optional keyword arguments for isolation level, statement timeout, and lock timeout; it applies transaction-local setup, commits on success, rolls back on failure, and always closes the session. Omitted arguments preserve database defaults. Repositories share this session and do not commit independently.
- Use a repository layer for SQLAlchemy queries, UUID lookup, balance updates, payment insertion, and audit insertion.

## Module hierarchy

```text
firm_payments_service/
├── __init__.py
├── main.py            # Build the FastAPI app, register routes and error handlers.
├── config.py          # pydantic-settings configuration.
├── api/
│   ├── __init__.py
│   ├── routes.py      # Sync payment endpoints, capture raw JSON/request ID, HTTP error mapping.
│   ├── schemas.py     # Request/response schemas and exact dollar-to-cent validation.
│   └── health.py      # Liveness and readiness endpoints.
├── payments/
│   ├── __init__.py
│   ├── service.py     # Transfer rules, credit aggregation, transactional audit and commit.
│   └── repository.py  # UUID lookup, ordered balance updates, payment and audit inserts.
├── db/
│   ├── __init__.py
│   ├── session.py     # SQLAlchemy engine and session factory.
│   └── models.py      # Platform firms/payments mappings and service-owned audit model.
├── auth/
│   └── __init__.py    # JWT verification, payer authorization and operational key checks.
└── observability/
    ├── __init__.py
    ├── logging.py     # JSON log configuration and request correlation.
    └── metrics.py     # Prometheus metrics and metrics endpoint registration.

db_migrations/         # Alembic migrations for service-owned audit table only; exclude platform tables.
tests/
├── unit/              # Input validation and transfer-rule checks.
└── functional/        # API, PostgreSQL rollback and concurrent-transfer checks.
```

The request flow is `api → auth → service → repository → database`.
A shared synchronous API dependency verifies the caller before body parsing;
the route validates the body and authorizes the payer before calling the service.
The service creates a session and owns one transaction per attempt; the repository uses that same
session without committing. ORM models stay internal;
the API returns response schemas. See [authentication and authorization](authentication_and_authorization.md), [observability](observability.md), and
the [API contract](api.md) for their respective decisions.

Keep `main.py` at the application package root as the composition entry point.
Group HTTP concerns in `api`, transfer behavior in `payments`, persistence setup
and mappings in `db`, platform security in `auth`, and logging and metrics in
`observability`. Add further nesting only when more features require it.

## Payment transaction

1. Use one PostgreSQL transaction per bulk request at SERIALIZABLE isolation, set before any transaction queries execute.
2. Resolve all payer and recipient UUIDs to internal IDs within the transaction without reading balances into Python. Each supplied UUID must resolve to exactly one firm; reject missing or ambiguous mappings rather than choosing an arbitrary row.
3. Trust stored balances as valid, nonnegative integer cents; do not revalidate stored data. Validate positive payment amounts and batch totals against the actual database integer ranges; PostgreSQL enforces the range of resulting balances during updates. See [data model](data-model.md).
4. Require `balance_cents >= total_cents` for the payer, including equality, in the debit UPDATE's WHERE clause. Use `RETURNING id` to require an updated row; no returned row raises `NoResultFound`, mapped to `INSUFFICIENT_FUNDS` with full rollback. Resolve payer existence independently of funds: do not filter UUID lookup by balance. A zero payer balance yields insufficient funds for a positive batch; a successful debit cannot leave the payer negative. Credits do not require a balance predicate.
5. Apply balance changes with SQL arithmetic on stored balances; never calculate resulting balances in Python. PostgreSQL rejects out-of-range results. Map numeric overflow (`SQLSTATE 22003`) during balance updates to `INVALID_AMOUNT` and roll back the entire transaction.
6. Aggregate credits per recipient for balance updates, while inserting one payment row per input entry, including repeated recipients and their separate descriptions. Apply debit and credits in ascending internal firm-ID order to reduce deadlock risk.
7. Insert one audit row per successful bulk request through the repository in the same transaction as payments and balance updates. The [data model](data-model.md#audit-table) defines the audit schema.
8. Commit before returning success. Roll back the entire transaction on any failure, including audit insertion failure; rejected or rolled-back transfers leave no balance changes, payment rows, or audit row.

## Concurrency and failures

- Automatically retry only PostgreSQL serialization failures (`SQLSTATE 40001`), including failures at commit. Roll back the whole transaction and start a fresh transaction, repeating UUID resolution, validation, balance updates, payment insertion, and audit insertion.
- Preserve the same service-generated request ID and original parsed JSON body across attempts. Only the successful attempt persists payment and audit rows.
- Configure the maximum total attempts, defaulting to 3 (one initial attempt and up to two retries), with a minimum of 1. Configure the internal delay between serialization retries, defaulting to 50 ms.
- Never automatically retry an uncertain commit outcome. Automatic serialization retries repeat only known aborted transactions; repeated HTTP submissions follow the [API's idempotency policy](api.md#payment-endpoint).
- Other failures, including deadlocks and lock timeouts, fail the request without automatic retry. HTTP responses follow [API](api.md#database-failure-responses); internal failure details are logged with the request ID according to [observability](observability.md).
- Configure PostgreSQL statement and lock timeouts, each defaulting to 60 seconds. Apply them transaction-locally on every attempt, including retries. Statement timeout bounds each statement rather than the total request duration; timeout failures follow the non-serialization failure policy.
- Compatibility with other platform balance writers must be validated during integration; see [assumptions](assumptions.md#other-balance-writers).

### Alternatives considered

- A conditional payer debit enforces funds in SQL; ordered updates and SERIALIZABLE isolation also protect transfers involving several shared firms.
- READ COMMITTED with explicit row locks is an alternative; SERIALIZABLE is the selected isolation level.
- In-process locks cannot coordinate multiple service instances.

## Execution model

- Use synchronous SQLAlchemy with Psycopg 3 and a synchronous endpoint; keep each database session scoped to one request.
- Run one Uvicorn worker per container; scale through additional containers when needed.
- The [traffic and response-time assumptions](assumptions.md#firm-population-and-payment-volume) support starting with synchronous access due to relatively low request rate; asynchronous access would complicate implementation and transaction handling for minimal expected value. Validate capacity and latency against those assumptions before deployment.
- Use pydantic-settings for configuration and pytest for validation, rollback, and concurrent-transfer checks against PostgreSQL.

## Requirements

FR-01–FR-07, NFR-01–NFR-04.

## Local development startup

Compose initializes a local stand-in for the platform database through a one-shot
`db-init` service after PostgreSQL is healthy. The app waits for successful
initialization and Dex readiness, runs `alembic upgrade head`, then starts Uvicorn.
An initialization or migration failure prevents app startup. This orchestration
is local only; the production image command does not initialize platform data or
run migrations automatically.

`make up` also starts pgAdmin on loopback port 5050 (`PGADMIN_PORT` overrides it).
Its configuration persists in a separate volume, with a preloaded connection to
the default Compose database. Login credentials are local defaults configurable
through `PGADMIN_DEFAULT_EMAIL` and `PGADMIN_DEFAULT_PASSWORD`; the database
connection prompts for the PostgreSQL password. If the database name or user is
customized, update the preloaded connection in pgAdmin. PostgreSQL stays internal.

`make sample` runs the standard-library Python request script inside the app
container. It obtains a fresh Dex ID token for the existing payer user and
submits the PDF worked example from `local/payment.json`. It prints HTTP status
and response and exits nonzero on request errors or an unexpected success status.
Payments are sent only by this explicit command, never by startup. Repeated
submissions follow the existing API policy and perform additional transfers.
