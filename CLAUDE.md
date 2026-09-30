# slopguard: notes for Claude Code

- The design and milestones are in `slopguard-plan.md`. Section 0 has the working rules.
- **Minimal custom logic:** delegate to ruff, vulture, PMD, git, and Claude Code hooks; slopguard only builds commands, runs them, and turns output into findings.
- **Checks run only in the Stop hook.** Do not add per-edit (PreToolUse/PostToolUse) hooks.
- **Tools are pinned exactly** (ruff 0.16.9, vulture 2.16 in `pyproject.toml`; PMD 7.28.0 in `checks/pmd_cpd.py`). Upgrade deliberately and rerun the tests.
- Adding a check is one new file in `src/slopguard/checks/` implementing `Check` from `checks/base.py`, plus a line in `hooks._enabled_checks`.
- Tests: `uv run pytest`. The real-PMD tests are skipped unless `pmd` is on `PATH`.
- `tests/fixtures/hooks/` holds real hook JSON captured from Claude Code; `tests/fixtures/*.py` are deliberately bad code, excluded from lint and from slopguard's own checks.
