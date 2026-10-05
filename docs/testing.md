# Testing

## Approach and organization

Use pytest for unit tests and HTTP functional tests against real PostgreSQL.
Use shared pytest fixtures for clients, committed seed data, database inspection,
and cleanup; use Polyfactory dataclass factories for generated firms and requests.
Keep monetary expectations explicit in integer cents rather than reusing application
conversion logic. Parameterize related success and failure cases to avoid duplication.

- `tests/unit/` contains isolated application checks without requiring payment data.
- `tests/functional/` contains database readiness and fixture checks, plus payment
  acceptance contracts for the PDF example, success, validation, rollback, and concurrency.
- `tests/functional/conftest.py` owns shared fixtures; `factories.py` supplies data
  factories and `assertions.py` checks responses and committed database state.

The requirements and application design define expected behavior. Successful transfers
must conserve total balances, preserve individual payment entries and descriptions,
and persist the original request in one audit row. Rejected or rolled-back transfers
must preserve the entire prior database state, including existing payment and audit rows.

## Running tests

Docker must be running and accessible. Test commands start PostgreSQL and build the app
image automatically. Coverage is enabled through pytest configuration.

```sh
# All tests, including unfinished acceptance contracts.
make test

# Only acceptance contracts.
make test PYTEST_ARGS="-m just_contract"

# Development checks without acceptance contracts (also used by Stop hooks).
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
`firms`, `payments`, and `firm_payments_audit` tables mirror the documented schema;
this harness does not validate production migrations. Platform money columns use
PostgreSQL INTEGER ranges. UUID uniqueness and other unspecified platform constraints
are intentionally absent, allowing tests of ambiguous UUID mappings.

Fixtures seed committed Polyfactory data and truncate all three tables before and
after every contract test, including failed tests. Application requests use independent
connections and real commits; an outer rollback/savepoint would hide commit and
concurrency behavior. The database is dropped after the suite. Payment authentication
is explicitly disabled; JWT verification is outside this suite. Database triggers
exercise payment/audit insertion failures, and independent clients synchronize
concurrent requests with a thread barrier.

The `just_contract` marker is reusable across features and excluded only from
automatic development test runs. Keep these acceptance criteria stable: change
contracts when requirements change or assertions are incorrect, and implement
service behavior to satisfy them. The PDF worked example preserves its three firms
and three payments exactly. Generated cases cover validation, precision,
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
