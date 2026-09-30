# slopguard

A Claude Code Stop hook that keeps Claude from finishing a turn while the code contains AI slop:

- **too complex:** complexity, argument count, statements, and nesting in changed files (ruff);
- **too long:** files over a line limit;
- **type slop:** deeply nested annotations and wide tuples in signatures and type aliases;
- **dead code:** anywhere in the configured paths (vulture);
- **copy-paste:** duplicated blocks that involve a changed file (PMD CPD).

When a check fails, the hook exits 2 and Claude gets a short list of what to fix. After one fix attempt it lets Claude stop, so it can never loop.

## Install

```sh
uv tool install git+<repo-url>   # brings pinned ruff 0.16.9 and vulture 2.16
```

Duplication needs PMD 7.28.0 (pinned) and Java 8+ on `PATH`. PMD is not on PyPI: download
<https://github.com/pmd/pmd/releases/download/pmd_releases/7.28.0/pmd-dist-7.28.0-bin.zip>, unzip it, and put its `bin/` on `PATH`. Without PMD, the duplication check is skipped with a warning.

## Set up a project

```sh
cd your-project
slopguard init     # adds [tool.slopguard] to pyproject.toml, a vulture whitelist, and the Stop hook
slopguard doctor   # checks ruff, vulture, Java, and PMD versions
slopguard config show
```

`init` never overwrites anything: it keeps an existing `[tool.slopguard]` table, whitelist, and hooks.
The generated `vulture_whitelist.py` exempts dead code that already exists, so only new dead code is reported.

## Configure

All settings live in `[tool.slopguard]` in `pyproject.toml`; see `slopguard config show` for every key and its default.
The key choice for existing code is `[tool.slopguard.edit] existing_violations`:

- `"allow"` (default): report only violations that are new compared with the last commit;
- `"block"`: report every violation in a changed file.

Changes to these settings are ordinary diffs; review them in PRs.
