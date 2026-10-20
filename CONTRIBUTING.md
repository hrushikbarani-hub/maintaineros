# Contributing

Start with the README's local setup and the architecture document. This project favors small, reviewable changes that improve an actual user workflow.

## Before opening a pull request

1. Explain the user problem and reproduction steps in an issue or PR description.
2. Add focused tests for data integrity, integrations, or behavior that could regress.
3. Run `python -m pytest -q`, `python -m ruff check .`, and `python -m ruff format --check .`.
4. For UI work, check keyboard navigation, empty/error states, and desktop/mobile layouts. Keep imported text escaped.
5. Run `python -m build` when changing packaging. Static assets must remain in the wheel.

Keep external requests out of unit tests. Use temporary databases and fake HTTP transports. Never commit credentials, real personal records, or workspace database files.

Use a clear commit message describing the resulting behavior. PRs should include what changed, why, and the checks run. If a change adds a new limitation, document it beside the relevant feature.

## Good first contributions

Accessible labels, clearer empty states, fixture-based integration tests, and documented source adapters are welcome. Discuss changes to score semantics or decision-linking rules before implementation because they affect how people interpret evidence.
