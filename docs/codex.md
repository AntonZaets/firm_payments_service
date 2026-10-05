# Development with Codex

OpenAI Codex was used as a coding agent during development. This guide records
the repository-supported workflow and safeguards; it does not claim a particular
model version or measured productivity improvement.

## Working approach

- Start from [AGENTS.md](../AGENTS.md) and the [documentation index](index.md).
  Read requirements, design decisions, and the relevant code before proposing changes.
- Use planning to clarify scope and material tradeoffs before implementation.
  Keep confirmed decisions and provisional assumptions explicit in the design docs.
- Prefer small, reviewable changes and existing project tools over new abstractions
  or dependencies. The ponytail approach used with Codex emphasizes the simplest
  solution that meets the requirements, without sacrificing monetary correctness,
  validation, security, or failure handling.
- Use the documented acceptance contracts to verify behavior. Fix implementation
  failures rather than weakening expectations; update design documentation when
  implementation reveals a missing decision.
- Review the diff and check results before accepting changes. Use Conventional
  Commits when committing; automatic checks support teammate review.

## Automatic checks

The repository configuration in [.codex/hooks.json](../.codex/hooks.json) runs
`make check` after `apply_patch`, `Write`, and `Edit` tool calls (`PostToolUse`).
Before Codex finishes each turn (`Stop`), including read-only turns, it runs:

```sh
make check
make test PYTEST_ARGS="-m 'not just_contract'"
```

These checks run synchronously. Failures return feedback for correction before
the turn finishes. The Stop checks also cover shell-based edits. Ruff and
whitespace hooks can modify files; review their changes. New files must be added
to Git for pre-commit to inspect them. The `just_contract` marker is reserved for
future deferred acceptance contracts; the current payment contracts run in the
default development set. Run `make test` for the complete suite, as CI does.

Docker must be running and accessible to Codex. Checks run on the host through
locked uv dependencies; tests run in containers with PostgreSQL and Dex. See the
[development guide](development.md) for setup and [Testing](testing.md) for details.

After installing or changing hook configuration, restart Codex, trust the project,
and use `/hooks` to review and trust the updated configuration.

## Protected acceptance contracts

[.codex/config.toml](../.codex/config.toml) selects the `protect-contracts`
permission profile, with `approval_policy = "on-request"` and
`approvals_reviewer = "user"`. It makes `tests/functional/` read-only.

Before any direct contract edit, present the exact proposed diff and obtain
explicit manual approval, then request a one-time escalation for that edit.
Feature or bug-fix approval does not authorize contract changes. Automatic
formatting through `make check` is permitted; changing expectations or fixtures
to make implementation pass is not. Follow the full
[contract protection rules](testing.md#contract-test-protection).

After configuration changes, restart Codex and verify effective permissions.
Legacy sandbox settings or `--sandbox` flags override permission profiles;
omit them when using this profile.
