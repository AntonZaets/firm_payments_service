# Firm Payments Service

This service implements bulk transfers between firms in the platform database.
The review focus is monetary correctness: an accepted request commits every
balance change, payment entry, and audit record together; a rejected request
leaves the database unchanged. The [requirements](docs/requirements.md) define
expected behavior, and the [documentation index](docs/index.md) links the full design.

## Solution and approach

`POST /api/v1/payments/bulk` accepts a payer UUID and individual payments.
FastAPI validates dollar strings and converts them exactly to integer cents.
The service resolves public UUIDs to internal firm IDs and uses SQL arithmetic
for balance changes, with a conditional debit to enforce sufficient funds.
Repeated recipients receive an aggregated credit while retaining separate
payment entries and descriptions.

A synchronous SQLAlchemy/Psycopg transaction uses PostgreSQL SERIALIZABLE
isolation and ordered balance updates. Known-aborted serialization failures
receive bounded retries; other database failures roll back. HTTP 201 with a
request ID is returned only after commit. One audit row stores the original
parsed request in the same transaction.

Payment requests require JWT verification and authorization for the requested
payer. Operational endpoints use a separate API key. JSON logs, correlated
request IDs, Prometheus metrics, and health endpoints support diagnosis.
Docker Compose supplies PostgreSQL, local Dex authentication, and pgAdmin for
reproducible development. See the [architecture](docs/design/architecture.md)
and [API contract](docs/design/api.md) for the detailed decisions.

## Issues addressed and tradeoffs

The implementation addresses these integration and correctness challenges:

- Concurrent transfers must not overspend or lose credits. Database transactions,
  conditional debits, ordered updates, and serialization retries coordinate
  across instances without relying on process-local locks.
- The platform owns `firms` and `payments`. Service migrations manage only the
  audit schema; local bootstrap supplies stand-in platform tables. Migration
  tests separately verify installation and preservation of existing audit data.
- Local authentication differs from deployment authentication. Compose explicitly
  uses Dex's RS256 ID tokens, while the standard profile uses ES256 tokens.
  Dex access tokens are opaque and cannot replace the ID token in sample requests.
- Host Git hooks and container tests use separate environments. Locked dependencies
  keep them consistent, but dependency changes require rebuilding the image.

## Assumptions

Stored balances are valid nonnegative integer cents. Actual platform constraints,
indexes, permissions, and compatibility with other balance writers need integration
review. The synchronous execution model assumes modest traffic; the provisional
peak estimate is 10 bulk requests per second, with response times ideally below
100 ms or within a few hundred milliseconds. These are planning assumptions,
not measured performance guarantees.

Authentication and payer authorization were added as design assumptions because
the original task did not specify them. Deployment owners must provide trusted
JWT settings, HTTPS ingress, private operational access, and log/metric collection.
See [design assumptions](docs/design/assumptions.md) for what remains to be validated.

## Possible improvements

- Measure representative batch sizes, concurrent writers, JWKS latency, and retry
  behavior before changing the execution model or deployment capacity.
- Consider JWKS caching if measured authentication latency warrants it; keys are
  currently fetched per request with a bounded timeout.
- Add client idempotency if safe resubmission becomes a requirement. Currently,
  repeated HTTP submissions are separate transfers, including `make sample`.
- Validate platform lookup indexes and operational targets with the owners before
  proposing schema changes, capacity adjustments, or alerts.

These are follow-up options, not implemented features or new requirements.

## Run and verify

Install Docker with Compose v2, GNU Make, Git, and uv 0.12.23 or newer, and ensure
Docker is running. From the repository root:

```sh
make setup
make up
make sample
make check
make test
```

Setup creates the host environment, installs Git hooks, and copies `.env.example`
if needed. Startup initializes local data and applies audit migrations. On a
fresh database, the sample returns HTTP 201, creates three payments and one audit
row, and leaves balances of 3674875, 170075, and 1405050 cents for Pinecrest,
Lopez, and Nair respectively. Repeating it transfers money again.

Open [API documentation](http://127.0.0.1:8000/docs) or
[pgAdmin](http://127.0.0.1:5050) to inspect the service. Verify readiness with the
local operational key:

```sh
curl --fail -H "X-API-Key: local-operational-key" http://127.0.0.1:8000/health/ready
```

Tests exercise exact money conversion, validation, authentication, rollback,
conservation, concurrent transfers, migrations, and local startup behavior against
real PostgreSQL where appropriate. Checks cover lint, formatting, typing,
security, and dependencies. GitHub Actions also applies migrations twice and
smoke-tests readiness and metrics.

See the [development guide](docs/development.md) for credentials, configuration,
commands, expected sample balances, dependency maintenance, and troubleshooting;
see [Testing](docs/testing.md) for suite selection and contract protection.

## Development with Codex

OpenAI Codex was used as a coding agent for development. The working approach
is documentation-first planning, small reviewable changes, reuse of existing
project tools, and verification against stable acceptance contracts. The ponytail
approach favors the simplest implementation that satisfies the requirements.
Repository guidance and permissions protect functional contracts, while automatic
hooks run checks after supported edits and checks plus development tests before
each turn finishes. Human review remains part of accepting the changes.

The [Codex workflow guide](docs/codex.md) explains the approach, automatic checks,
hook setup, and contract-edit approval rules.


## Feedback

### How much time did you spend on this task?

8 hours


### How proud are you of your work?

Good enough
