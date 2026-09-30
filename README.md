# slopguard

A Claude Code Stop hook that keeps Claude from finishing a turn while the code contains AI slop:

- **too complex:** complexity, argument count, statements, and nesting in changed files (ruff);
- **too long:** files over a line limit;
- **type slop:** deeply nested annotations and wide tuples in signatures and type aliases;
- **dead code:** anywhere in the configured paths (vulture);
- **copy-paste:** duplicated blocks that involve a changed file (PMD CPD).

When a check fails, the hook exits 2 and Claude gets a short list of what to fix. After one fix attempt it lets Claude stop, so it can never loop.

## Install

slopguard is not on PyPI; install it with uv straight from GitHub. The pinned ruff 0.16.9 and vulture 2.16 come with it.

**As a global tool (recommended).** One install serves every project, and `slopguard` lands on `PATH`:

```sh
uv tool install git+https://github.com/kimzed/python-slopguard
uv tool install git+https://github.com/kimzed/python-slopguard@<commit-or-tag>   # pin a version
uv tool upgrade slopguard                                                        # later
```

**As a dev dependency of one project.** Everyone working on the repo gets the same version from the lock file:

```sh
uv add --dev git+https://github.com/kimzed/python-slopguard
uv run slopguard init
```

`slopguard` is then not on `PATH` outside `uv run`, so after `init`, change the hook command in `.claude/settings.json` from `slopguard hook stop` to `uv run slopguard hook stop`.

**Without installing**, e.g. to try it: `uvx --from git+https://github.com/kimzed/python-slopguard slopguard doctor`.

### PMD (for the duplication check)

Duplication needs PMD 7.28.0 (pinned) and Java 8+ on `PATH`. PMD is not on PyPI: download
<https://github.com/pmd/pmd/releases/download/pmd_releases/7.28.0/pmd-dist-7.28.0-bin.zip>, unzip it, and put its `bin/` on `PATH`. Without PMD, the duplication check is skipped with a warning (see `on_missing_tool`).

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

All settings live in `[tool.slopguard]` in `pyproject.toml`. Every key is optional: a missing key takes its default, an unknown key or a value of the wrong type is a config error (the hook then skips its checks and prints why). `slopguard config show` prints the effective config.
Changes to these settings are ordinary diffs; review them in PRs.

```toml
[tool.slopguard]
exclude = ["tests/fixtures/*"]

[tool.slopguard.edit]
max_args = 5
existing_violations = "block"

[tool.slopguard.duplication]
enabled = false
```

### When the checks run

The hook runs when Claude tries to finish a turn. "Changed files" means files that `git status` reports as modified or untracked. If no `.py` file changed, nothing runs. Outside a git repo, the `edit` limits are skipped (there are no changed files to check) and the whole-project checks still run.

### General

| Key | Default | Meaning |
|---|---|---|
| `exclude` | `[]` | Glob patterns (fnmatch, relative to the project root, e.g. `"migrations/*"`) excluded from every check. |
| `allow_suppression_comments` | `false` | Whether a `# noqa` comment can silence a finding. A comment like `def f(a, b, c, d, e):  # noqa: PLR0913` normally tells ruff to skip that line, which gives Claude an easy way to dodge a limit instead of fixing the code. With `false`, slopguard ignores these comments and the finding is reported anyway. Set `true` to let them work. Applies to the ruff limits (`max_complexity`, `max_args`, `max_positional_args`, `max_statements`, `max_nested_blocks`); the other checks have no suppression comments. |
| `max_findings` | `10` | Maximum findings listed in the report shown to Claude; the rest are summarized as "...and N more". |
| `on_missing_tool` | `"warn"` | What happens when PMD is not installed. This only concerns PMD (the duplication check): ruff and vulture are installed with slopguard, so they are never missing. `"warn"`: skip the duplication check, print a warning, and run the other checks as usual. `"skip"`: the same, without the warning. `"error"`: block Claude with a `missing-tool` finding until PMD is installed; Claude cannot fix this itself, so use it only if every machine has PMD. If you don't use PMD at all, set `duplication.enabled = false` instead. |
| `instructions_to_claude_on_block` | `"Fix by refactoring. Do not add suppression comments."` | A line of instructions added at the end of the message Claude gets when slopguard blocks it, after the list of problems. Use it to tell Claude how you want problems fixed, e.g. `"Split long functions into smaller ones; never add # noqa."` |

### `[tool.slopguard.edit]`: limits on changed files

These apply only to changed `.py` files. The first five are passed to ruff as the settings of the rule shown.

| Key | Default | Rule | Meaning |
|---|---|---|---|
| `enabled` | `true` | | Turns off every check in this table. |
| `max_complexity` | `6` | `C901` | Maximum cyclomatic complexity of a function: how many decisions it makes, not how long it is. It starts at 1 and adds 1 for each `if`, `elif`, `for`, `while`, `except`, and `match` case (`and`/`or` do not count). A 6-line function full of `if`s can fail this limit, and a 40-line function with no branches passes it (length is `max_statements`). |
| `max_args` | `4` | `PLR0913` | Maximum parameters in a function definition, positional and keyword-only. `self`/`cls`, `*args`, `**kwargs`, and names starting with `_` are not counted. |
| `max_positional_args` | `4` | `PLR0917` | Maximum positional parameters (keyword-only parameters after `*` are not counted), same exclusions as `max_args`. Lower it below `max_args` to push callers toward keyword arguments. |
| `max_statements` | `25` | `PLR0915` | Maximum statements in a function body, counting nested statements. |
| `max_nested_blocks` | `3` | `PLR1702` | Maximum depth of nested `if`/`for`/`while`/`try`/`with` blocks inside a function. |
| `max_file_lines` | `400` | `file-length` | Maximum lines in a file. |
| `max_annotation_depth` | `3` | `annotation-depth` | Maximum nesting of a type annotation or type alias: `list[int]` is 2, `tuple[list[str \| None], int]` is 3. Unions (`X \| None`, `Optional`), `Annotated`, and `Callable` parameter lists add no level. |
| `max_annotation_elements` | `7` | `annotation-size` | Maximum leaf types in one annotation: `dict[str, tuple[int, float]]` has 3. |
| `max_return_tuple` | `3` | `return-tuple` | Maximum elements of a `tuple[...]` in a return type or type alias (parameters are not checked; `tuple[int, ...]` is fine). |
| `existing_violations` | `"allow"` | | `"allow"`: report only violations that are new compared with the last commit, so touching a legacy file does not force a rewrite of it. `"block"`: report every violation in a changed file. |
| `exclude` | `[]` | | Glob patterns excluded from these limits only. |

The last three limits cover what ruff has no rule for; the annotation checks push Claude toward a dataclass, `NamedTuple`, `TypedDict`, or Pydantic model instead of nested tuples and dicts.

### `[tool.slopguard.dead_code]`: vulture

Runs over the whole of `paths` (not only changed files), because code usually becomes dead when its last caller in *another* file is removed.

| Key | Default | Meaning |
|---|---|---|
| `enabled` | `true` | Turns the check off. |
| `paths` | `["src"]` | Directories or files to scan; missing ones are ignored. |
| `min_confidence` | `60` | Vulture's minimum confidence (0–100). Vulture rates unused functions, classes, methods, and variables 60%, unused imports 90%, and unused arguments and unreachable code 100%, so the default reports all of them; raise it to report fewer, surer cases. |
| `ignore_decorators` | `[]` | Decorator patterns whose functions are never reported, e.g. `["@app.route", "@pytest.fixture"]`. |
| `ignore_names` | `[]` | Name patterns never reported, e.g. `["test_*", "visit_*"]`. |
| `whitelist` | `"vulture_whitelist.py"` | Path of a file listing dead code that vulture should ignore. Dead code is checked across the whole project, so without this file, adding slopguard to an existing project would block Claude on dead code it never wrote. `slopguard init` creates the file for you, listing all dead code that exists at that moment: old dead code is tolerated, and only dead code added afterwards is reported. Edit it by hand: delete a line once you have removed that old code (so it is checked again), or add a line when vulture is wrong, e.g. a function only called by a framework. If the file does not exist, nothing is ignored. |

### `[tool.slopguard.duplication]`: PMD CPD

PMD scans all of `paths`, but a duplicated block is reported only when at least one of its copies is in a changed file, so old duplication does not block unrelated work.

| Key | Default | Meaning |
|---|---|---|
| `enabled` | `true` | Turns the check off. |
| `paths` | `["src", "tests"]` | Directories to scan; missing ones are ignored. |
| `min_tokens` | `70` | Minimum length of a duplicated block, in tokens. Lower finds smaller copies and more noise. |
| `min_occurrences` | `3` | Minimum number of copies before it is reported. The default tolerates one copy-paste and blocks the third; set `2` to block any duplication. |
| `exclude` | `[]` | Glob patterns whose copies are ignored (and not counted toward `min_occurrences`). |
