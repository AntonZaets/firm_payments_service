# Testing

## Approach and organization

Use pytest for unit tests and HTTP functional tests against real PostgreSQL.
Use shared pytest fixtures for clients, committed seed data, database inspection,
and cleanup; use Polyfactory dataclass factories for generated firms and requests.
Keep monetary expectations explicit in integer cents rather than reusing application
conversion logic. Parameterize related success and failure cases to avoid duplication.

- `tests/unit/` contains isolated application checks without requiring payment data.
- `tests/integration/` verifies production audit migrations and local database
  initialization, PDF sample assets, and restart preservation against disposable PostgreSQL.
- `tests/functional/` contains database readiness and fixture checks, plus payment
  acceptance contracts for the PDF example, success, validation, rollback, and concurrency.
- `tests/functional/conftest.py` owns shared fixtures; `factories.py` supplies data
  factories and `assertions.py` checks responses and committed database state.

The requirements and application design define expected behavior. Successful transfers
must conserve total balances, preserve individual payment entries and descriptions,
and persist the original request in one audit row. Rejected or rolled-back transfers
must preserve the entire prior database state, including existing payment and audit rows.

## Running tests

Docker must be running and accessible. Test commands start PostgreSQL and Dex and build the app
image automatically. Coverage is enabled through pytest configuration.

```sh
# All tests.
make test

# Only deferred acceptance contracts, when any are marked.
make test PYTEST_ARGS="-m just_contract"

# Development checks, excluding any deferred acceptance contracts.
make test PYTEST_ARGS="-m 'not just_contract'"

# Pre-commit lint, formatting, typing, security, and dependency checks.
make check
```

`make check` can modify files. Stage new files before running it so pre-commit can
inspect them. Acceptance contracts are ordinary tests, not expected failures or skips;
their failures show regressions against the documented behavior.

## Functional database harness

Payment contract tests use real PostgreSQL in a uniquely named disposable database
on the configured server. The test owner needs CREATE DATABASE permission. Test-owned
`firms`, `payments`, and `firm_payments_service.firm_payments_audit` tables mirror
the documented schema. Test connections use `public,firm_payments_service` as their search path so
existing unqualified audit inspection and failure triggers resolve the service
table. This harness does not validate production migrations. The separate
migration test checks fresh installation, existing-row preservation, identity
sequence continuity, downgrade/re-upgrade, and autogeneration exclusion of
platform tables and unrelated schemas. Platform money columns use
PostgreSQL INTEGER ranges. UUID uniqueness and other unspecified platform constraints
are intentionally absent, allowing tests of ambiguous UUID mappings.

Fixtures seed committed Polyfactory data and truncate all three tables before and
after every contract test, including failed tests. Application requests use independent
connections and real commits; an outer rollback/savepoint would hide commit and
concurrency behavior. The database is dropped after the suite. Existing payment contract fixtures explicitly disable payment authentication.
New authentication contracts must reuse those database/client fixtures, explicitly
enable the Dex profile, and use real Dex-issued ID tokens for authentication and
payer authorization. Compare the entire database state on rejection, including
existing payments and audit rows. Test expiration by advancing only the verifier's
clock past a real token's expiration, retaining signature verification without a
long sleep. Adding these contracts requires the approval described below.
Unit tests verify standard ES256 tokens, malformed claims, key-fetch failures,
configuration defaults and profile isolation. Operational key checks remain
independent of payment authentication. Database triggers
exercise payment/audit insertion failures, and independent clients synchronize
concurrent requests with a thread barrier.

The payment acceptance contracts are green and run in the default development
test set. The `just_contract` marker remains available only for future deferred
acceptance contracts. Keep these acceptance criteria stable: change contracts
when requirements change or assertions are incorrect, and implement service
behavior to satisfy them. The PDF worked example preserves its three firms and
three payments exactly. Generated cases cover validation, precision,
conservation, audit, rollback, and concurrent balance updates.

## Contract test protection

- Treat `tests/functional/` as read-only, including creation, deletion, renaming,
  and fixture/assertion changes. Before any direct write, present the exact
  proposed diff and obtain explicit manual approval for that change. Approval to
  implement a feature or fix failing tests does not authorize changing contracts.
- Pre-commit hooks may format and automatically fix these files through `make check`;
  this exception does not authorize changing test expectations or fixtures to make
  an implementation pass.
- Request a one-time escalation for an approved contract edit; do not request or
  reuse broad command-prefix approvals to authorize contract changes. Never weaken
  the permission profile to bypass this requirement.
- `.codex/config.toml` selects the `protect-contracts` permission profile with
  `approval_policy = "on-request"` and `approvals_reviewer = "user"`. Restart Codex
  after changing this configuration and verify the effective permissions. Legacy
  `sandbox_mode` settings or `--sandbox` flags override permission profiles; omit
  them when using this profile.
