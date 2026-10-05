# Implementation guidance

- Treat `docs/` as the source of truth for implementation. Start with [the documentation index](docs/index.md) and follow the requirements, technology stack, and design decisions.
- If implementation reveals missing facts, rules, or decisions in the design, extend the relevant document in `docs/design/` as part of the change so the design describes the implemented behavior. Resolve any conflicts with documented requirements rather than silently overriding them.
- Follow the [development guide](docs/development.md) for setup, local authentication, configuration, migrations, dependency updates, and troubleshooting.
- Follow the [Codex workflow guide](docs/codex.md) for agent-assisted development, automatic check setup, and contract protection. Keep README.md as a teammate-facing review overview of the solution, issues, assumptions, improvements, verification, and Codex usage; keep detailed runbooks in `docs/`.
- Use Conventional Commits for all commit messages.

# Automatic Codex hooks

- The trusted project configuration in `.codex/hooks.json` runs `make check` after `apply_patch`, `Write`, and `Edit` tool calls (`PostToolUse`).
- Before finishing each turn (`Stop`), hooks run `make check` and `make test PYTEST_ARGS="-m 'not just_contract'"`, including read-only turns. Failures return feedback and continue the turn; fix failures before finishing.
- Docker must be running and accessible. Checks may modify files; new files must be added to Git for pre-commit to inspect them.
- After changing hooks, restart Codex and review and trust the updated configuration through `/hooks`.

# Testing

- Follow [the testing approach and contract test protection rules](docs/testing.md)
  when writing, running, or changing tests.
