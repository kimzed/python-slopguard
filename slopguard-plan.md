# slopguard: implementation plan

`slopguard` is a placeholder name. It is a reusable package that plugs into Claude Code hooks and pushes back on AI slop: over-complex functions, long files, dead code, and copy-paste duplication. It lives in its own repo, is installed once, and is configured per project.

## 0. Rules for Claude Code when implementing this plan

1. Work milestone by milestone (section 9). Do not start a milestone before the previous one's acceptance criteria pass.
2. Anything listed in section 10 ("Verify before relying on it") must be checked against the tool's `--help` or current docs before use. Do not guess flags, config keys, or JSON schemas.
3. Every check must have a pytest test with a fixture that triggers it and one that does not.
4. Keep each check in its own file behind a common interface, so adding a check is one new file.
5. **Minimal custom logic.** Delegate to third-party tools and existing mechanisms (ruff, vulture, PMD, git, Claude Code hooks) wherever they already do the job. slopguard is a thin adapter: build the tool's input, run the tool, turn its output into findings. Before adding logic, check whether a tool flag or feature already covers it.
6. **Pin every external tool to an exact version** (section 8). Never loosen a pin to make something work; upgrade deliberately and rerun the tests.
7. Prefer the standard library. `tomllib` for config (Python 3.11+), `subprocess` for external tools, `xml.etree` for PMD output.

## 1. Goals and non-goals

**Goals**
1. One install, many projects. Behavior is controlled by config, not by editing scripts.
2. **Veto, not just feedback.** All checks run once, when Claude tries to finish (Stop hook). If anything fails, Claude is not allowed to finish until it is fixed. There are no per-edit checks.
3. Messages to Claude are short, actionable, and hard to game.

**Non-goals**
1. CI and pre-commit integration. The primary use is Claude Code hooks. People can call the underlying tools themselves.
2. Replacing the project's own lint setup (ruff and mypy stay where they are).
3. Auto-fixing code. The tool blocks, Claude fixes.
4. Supporting languages other than Python in v1.

## 2. Architecture

One hook, run when Claude tries to finish a turn:

| Hook event | Command | Checks | Effect of exit 2 |
|---|---|---|---|
| Stop | `slopguard hook stop` | ruff limits and file length on changed `.py` files; dead code and duplication on the project | Claude is not allowed to finish; stderr goes to Claude (verified in M0) |

Flow: read hook JSON from stdin, load config, run enabled checks, collect `Finding` objects, print a capped report to stderr, and exit 2 if there are findings, otherwise 0. Because it only runs at the end, Claude can pass through messy intermediate states mid-refactor, and edits made any way (Edit, Write, or shell commands) are all caught.

"Changed files" come from git: `git status --porcelain` (modified and untracked files). Outside a git repo there is no changed-file list and no committed version to compare with, so the limits on changed files are skipped with a warning, while dead code and duplication run on everything.

**Existing violations** (`edit.existing_violations`, applies to ruff limits and file length):
1. `"allow"` (default): run ruff on the file as committed (`git show HEAD:<path>`, empty for untracked files) and on the file as it is now, and report only violations that are new. A violation is identified by `(rule code, stripped text of the reported line)`, for example `("C901", "def load(path, cfg):")`, because line numbers shift between versions but the flagged `def` line rarely does. For file length: report only if the file is over the limit and longer than the committed version. Legacy files stay editable, and new slop is blocked.
2. `"block"`: report every violation in changed files, whatever was there before. Touching a legacy file forces a refactor first.

Early exits keep the hook cheap:
1. Exit 0 immediately when no `.py` file changed.
2. Exit 0 when `stop_hook_active` is true (loop guard, see section 7, decision 5).

Tool binaries are resolved from slopguard's own environment, not `PATH`. `ruff` and `vulture` are package dependencies, invoked via `ruff.find_ruff_bin()` and `sys.executable -m vulture`, so `uv tool install` brings everything except PMD.

## 3. Checks

### 3.1 Stop: ruff limits (`checks/ruff_limits.py`)

`ruff check` on the changed `.py` files (and, in `"allow"` mode, on their committed versions), with only these rules selected and limits taken from slopguard's config:

1. C901: cyclomatic complexity (`max_complexity`)
2. PLR0913: too many arguments (`max_args`)
3. PLR0915: too many statements (`max_statements`). This counts statements, not lines.
4. PLR1702: too many nested blocks (`max_nested_blocks`). Still preview-only in ruff 0.16.
5. PLR0917: too many positional arguments (`max_positional_args`). Stable since ruff 0.16.

Starting defaults: complexity 6, args 4, positional args 4, statements 25, nesting 3. Treat them as tunable, not sacred. Ruff's own defaults for comparison: 10, 5, 5, 50, 5.

Design notes:
1. Always pass an explicit `--select C901,PLR0913,PLR0915,PLR1702,PLR0917`. Ruff 0.16 grew the default rule set from 59 to 413 rules.
2. Use `--isolated` plus inline `--config "key = value"` overrides (keys `lint.mccabe.max-complexity`, `lint.pylint.max-args`, `lint.pylint.max-statements`, `lint.pylint.max-nested-blocks`, `lint.pylint.max-positional-args`). This is deterministic across projects.
3. Enable PLR1702 with `--config "lint.preview = true" --config "lint.explicit-preview-rules = true"`, not the global `--preview`.
4. Use `--no-fix` and `--output-format json`. The current files are passed as paths; committed versions are piped in with `--stdin-filename <path> -`. Parse defensively: `code`, `filename` and `location` can be null.
5. Exit codes: 0 = clean, 1 = findings, 2 = config or internal error. Exit 2 is a tool error, never a finding.
6. `# noqa` handling: see section 7, decision 4.

### 3.2 Stop: file length (`checks/file_length.py`)

Count lines in each changed Python file and fail above `max_file_lines`. Pure Python, no dependency. The message should say what to do: split the module by responsibility.

### 3.3 Stop: dead code (`checks/vulture_dead.py`)

1. Run vulture on configured `paths` (default `src`, tests excluded) with `min_confidence = 60`. At 100% it would only report unused arguments and unreachable code, which misses the real slop (unused functions and classes).
2. Pass `--ignore-decorators` and `--ignore-names` (each a comma-joined list of globs) from config. The whitelist file is passed as an ordinary path argument next to the scanned paths.
3. Vulture needs the whole project to judge usage, which is why this runs at Stop.
4. Exit codes: 0 = clean, 3 = dead code found. 1 (invalid input, for example a syntax error) and 2 (bad arguments) are tool errors and must not be reported to Claude as findings.
5. There is no JSON output. Parse lines with a regex along the lines of `^(.+?):(\d+): (.+) \((\d+)% confidence(?:, \d+ lines?)?\)$`, and pin it with a test against real vulture output.
6. Scope: report dead code anywhere in `paths`. If Claude deletes the only caller of a helper in file A, the now-dead helper in unchanged file B must still be caught. Legacy dead code is exempted by vulture's own mechanism: `slopguard init` generates the whitelist with `vulture --make-whitelist`.

### 3.4 Stop: duplication (`checks/pmd_cpd.py`)

Engine is PMD CPD (chosen over jscpd because it reports each duplicated block once with all of its locations, so counting copies is trivial).

1. Run `pmd cpd --language python --format xml --minimum-tokens N --dir <path>` (repeat `--dir` per configured path; default `src` and `tests`), `min_tokens` default 70.
2. Exit codes: 0 = clean and 4 = duplications found; both mean "parse the XML". 5 = recoverable errors (for example a file PMD cannot lex): parse the XML as usual. The `<error>` elements are not surfaced: such files usually have a syntax error that Claude sees anyway, and checks have no warning channel for it. 1 (exception) and 2 (usage error) are tool errors, never findings. Do not use the deprecated `--skip-lexical-errors`.
3. Parse each `<duplication lines tokens>` element and count its `<file path line endline ...>` children.
4. Report only duplications with at least `min_occurrences` locations (default 3) that involve a changed file. New duplication always involves a file Claude touched, so this does not blame Claude for old code.
5. Deduplicate locations defensively by `(path, line)`: an older PMD issue reported the same block repeated in the XML.
6. Handle both XML shapes: PMD 7.3+ puts elements in the `https://pmd-code.org/schema/cpd-report` namespace, older versions do not.
7. Known limitation: `--ignore-identifiers` and `--ignore-literals` only work for Java and C++, so renamed copy-paste in Python is not detected.
8. PMD needs Java 8 or later. It is installed from the GitHub release zip or `brew install pmd`; there is no pip package. If Java or PMD is missing, behavior follows `on_missing_tool`.

### 3.5 Stop: annotation complexity (`checks/annotations.py`)

Nested tuples and dicts where a named structure belongs (`tuple[dict[str, list[int]], int]`). No ruff rule covers this, so slopguard walks the `ast` of each changed file itself, as `file_length` does. Findings: `annotation-depth` (`max_annotation_depth`, default 3), `annotation-size` (`max_annotation_elements`, default 7), and `return-tuple` (`max_return_tuple`, default 3).

1. Measured: argument and return annotations (sync and async), annotated assignments and class fields, and alias values in all three forms: `type X = ...`, `X: TypeAlias = ...`, and module-level `X = <generic subscript or | union>`.
2. Scoring matches flake8-annotations-complexity: `List[int]` is 2 and `Tuple[List[Optional[str]], int]` is 4. `X | None` adds no level, so `dict[str, list[int]] | None` is 3. `Annotated[T, ...]` scores as `T`, `Literal[...]` as 1, and string annotations are parsed and scored. Size counts leaf types, not generic heads.
3. `return-tuple`: a non-variadic `tuple[...]` with more than N elements in a return annotation or an alias value.
4. Every message ends with a hint to use a dataclass, NamedTuple, TypedDict or Pydantic model, "not with a type alias". Aliases are measured too, so moving the mess into an alias does not pass.
5. Not the flake8 plugin: tested at 0.2.0 on 2026-09-30, it scores depth the same way but misses all three alias forms and has no tuple-size rule, and it would add flake8 to the stack.
6. `existing_violations` works as in ruff_limits: the committed content is analysed too, and findings are matched by (code, line text).

## 4. Config

Config lives in the `[tool.slopguard]` table of the project's `pyproject.toml`, next to other tools' settings; built-in defaults fill in missing keys. There is no separate config file. `slopguard config show` prints the merged result.

```toml
[tool.slopguard]
exclude = ["**/migrations/**"] # applies to every check, unioned with section excludes
respect_noqa = false          # false: Claude cannot silence findings with # noqa
max_findings = 10             # cap per report; the report ends with "...and N more"
on_missing_tool = "warn"      # "warn" | "skip" | "error"
feedback_footer = "Fix by refactoring. Do not add suppression comments."

[tool.slopguard.edit]         # limits for changed files, checked at Stop
enabled = true
max_complexity = 6
max_args = 4
max_positional_args = 4
max_statements = 25
max_nested_blocks = 3
max_file_lines = 400
max_annotation_depth = 3      # List[int] is 2
max_annotation_elements = 7   # leaf types in one annotation
max_return_tuple = 3          # elements of a tuple in a return type or alias
existing_violations = "allow" # "allow": block only new violations | "block": block any
exclude = []                  # e.g. ["tests/**"] if tests should be exempt

[tool.slopguard.dead_code]    # Stop
enabled = true
paths = ["src"]
min_confidence = 60
ignore_decorators = ["@app.*", "@router.*"]
ignore_names = []
whitelist = "vulture_whitelist.py" # generated by `slopguard init`

[tool.slopguard.duplication]  # Stop
enabled = true
paths = ["src", "tests"]
min_tokens = 70
min_occurrences = 3
exclude = []
```

Config is validated on load, and unknown keys are an error with a clear message (typos should not silently disable a check).

**Config is for humans.** Claude could in principle game the checks by raising limits or appending to the whitelist. slopguard does not lock or detect this: such changes are visible in the diff and are caught in PR review.

## 5. CLI

1. `slopguard hook stop`: the hook entry point (reads JSON on stdin).
2. `slopguard init`: add a starter `[tool.slopguard]` table to `pyproject.toml` (only if absent), generate the vulture whitelist with `--make-whitelist`, and merge the hook entry into `.claude/settings.json` without overwriting existing ones. The Stop entry gets an explicit `timeout` large enough for PMD's JVM start-up on a big repo.
3. `slopguard doctor`: check that ruff, vulture, Java, and PMD are installed and report versions, and print install hints for anything missing (PMD: GitHub release zip or `brew install pmd`).
4. `slopguard config show`: print the effective config.

## 6. Repo layout

```
slopguard/
  pyproject.toml             # requires-python >= 3.11 (tomllib); deps: ruff==0.16.9, vulture==2.16
  uv.lock                    # committed; locks dev dependencies
  README.md
  CLAUDE.md                  # short project notes for Claude Code
  src/slopguard/
    cli.py                   # argument parsing, subcommands
    config.py                # load, merge with defaults, validate
    hooks.py                 # stdin JSON parsing, exit-code handling
    report.py                # Finding dataclass, formatting, caps
    vcs.py                   # changed files and HEAD content via git
    init.py                  # settings.json merge
    checks/
      base.py                # Check protocol: run(path, before, after, cfg) -> list[Finding]
      ruff_limits.py
      file_length.py
      annotations.py
      vulture_dead.py
      pmd_cpd.py
  tests/
    fixtures/                # slop samples, clean samples
      hooks/                 # real hook JSON captured by the M0 probe
    test_config.py
    test_hooks.py
    test_ruff_limits.py
    test_file_length.py
    test_annotations.py
    test_vulture_dead.py
    test_pmd_cpd.py          # includes captured PMD XML samples
```

## 7. Open decisions

Each decision has a recommendation; confirm or override before the milestone that needs it.

1. Are tests exempt from the `[edit]` limits? Recommendation: exempt from `max_args` and `max_statements` only (fixtures and parametrized tests legitimately grow), keep complexity and nesting.
2. Exact default for `max_file_lines`. Recommendation: keep 400 and tune in M6.
3. Two-tier duplication rule: also flag pairs (2 copies) when the block is very large (for example 150+ tokens)? Recommendation: off in v1.
4. `respect_noqa`. Recommendation: `false` so suppression is a deliberate human act in config, pending confirmation of what `--ignore-noqa` covers (section 10).
5. Stop-hook loop policy. Recommendation: when `stop_hook_active` is true (one fix attempt already made), print the remaining findings and exit 0 instead of blocking again.
6. Distribution. Recommendation: installed CLI only for v1; a plugin wrapper after M6 (plugins can bundle hooks, see section 8).

## 8. Distribution

**Pinned versions.** Tool output formats and rule behavior change between releases (ruff 0.16 alone changed its default rules and JSON nullability), so every external tool is pinned to an exact version, and upgrades are deliberate: bump the pin, rerun the tests, commit.

| Tool | Pin | How it is enforced |
|---|---|---|
| ruff | `==0.16.9` | exact pin in `pyproject.toml` dependencies; installed with slopguard |
| vulture | `==2.16` | exact pin in `pyproject.toml` dependencies; installed with slopguard |
| PMD | `7.28.0` | not on PyPI, so it cannot be a dependency. slopguard stores the expected version as a constant, and `doctor` fails if `pmd --version` differs. The install hint gives the exact download: `https://github.com/pmd/pmd/releases/download/pmd_releases/7.28.0/pmd-dist-7.28.0-bin.zip` |
| Java | 8 or later | `doctor` checks `java -version`; any version ≥ 8 is accepted, since PMD is what we pin |
| Python | `>=3.11` | `requires-python` in `pyproject.toml` |
| dev tools (pytest) | locked | `uv.lock` committed for development |

Exact pins in `pyproject.toml` are what count: `uv tool install` resolves the package's declared dependencies and does not read `uv.lock`. Exact pins are fine here because slopguard is an installed tool, not a library other packages depend on.

1. Install with `uv tool install` from the git URL. Use the installed binary in hook commands, not `uvx` per call, to avoid startup cost on every stop.
2. `slopguard init` wires up a project in one command.
3. Optional later step: publish to PyPI.
4. Optional later step: a Claude Code plugin that bundles the hook definitions so they can be enabled without editing `settings.json`. Plugins can ship `hooks/hooks.json` and reference their own files via `${CLAUDE_PLUGIN_ROOT}`; whether a plugin can declare or install the slopguard CLI as a dependency is unconfirmed (section 10).

## 9. Milestones and acceptance criteria

0. **M0: hook probe.** Done (2026-09-30). A throwaway script, registered for PreToolUse, PostToolUse and Stop, logged stdin JSON and exited 2 when armed. The results are in section 10, and the fixtures are in `tests/fixtures/hooks/`. The probe has been deleted.
1. **M1: skeleton.** Done (2026-09-30). Package, CLI with `config show`, config loading from `[tool.slopguard]` in `pyproject.toml` merged with defaults, and validation.
   Acceptance: unit tests for default merging and unknown-key errors pass; `slopguard config show` runs from an installed tool; `pyproject.toml` pins ruff and vulture exactly, and `uv.lock` is committed.
2. **M2: Stop gate with limits.** Done (2026-09-30), including the live check. `hook stop`, `vcs.py` (changed files, committed content), `ruff_limits`, `file_length`, both `existing_violations` modes, the loop guard, and the no-changed-`.py` early exit.
   Acceptance, using the M0 Stop JSON on a temporary git repo:
   1. A changed file with slop returns exit 2 with a readable report, and a clean change returns exit 0.
   2. No changed `.py` file returns exit 0 without running ruff; `stop_hook_active: true` returns exit 0.
   3. In `"allow"` mode, a small change to a file with a pre-existing violation passes, and a change that adds a new violation is reported.
   4. In `"block"` mode, both are reported.
   5. Live check: with the hook registered in this repo, Claude is not allowed to finish while a slop file is present.
3. **M3: dead code.** Done (2026-09-30). `vulture_dead` added to the Stop gate.
   Acceptance: a fixture with an unused function is flagged, a decorator-ignored one is not, a whitelisted one is not, and a vulture tool error (exit 1 or 2) is not reported as a finding.
4. **M4: duplication.** Done (2026-09-30), tested against a real PMD 7.28.0. `pmd_cpd` with XML parsing for both namespace shapes and exit-code handling (0, 4, 5 parsed; 1, 2 errors).
   Acceptance: a fixture with three copies is flagged and one with two copies is not (at `min_occurrences = 3`).
5. **M5: ergonomics.** Done (2026-09-30). `init` (config, whitelist, hook), `doctor`, `max_findings` capping, missing-tool handling.
   Acceptance: `doctor` fails clearly when the installed PMD is not 7.28.0; `init` on a project with existing hooks (for example a user-level Stop sound hook) preserves them, `init` on a project with existing dead code produces a whitelist after which the Stop check is clean, and `doctor` reports a missing Java runtime clearly.
6. **M5b: annotation complexity.** Done (2026-09-30). `annotations` added to the `[edit]` group (section 3.5).
   Acceptance: depth, size and return-tuple limits are enforced on signatures, annotated assignments and all three alias forms; plain subscripts such as `x = data[0]` are not treated as aliases; both `existing_violations` modes work.
7. **M6: real-world trial.** Install in one real project, run for a week, and tune defaults from what actually fires.

## 10. Verify before relying on it

Checked against docs on 2026-09-30 (ruff 0.16.9, vulture 2.16, PMD 7.28.0). Re-check if the installed versions differ.

**Still unverified:**
1. Claude Code plugins (after M6): whether a plugin can declare or install an external CLI dependency.

**Verified by running the pinned tools (2026-09-30, during M2–M5):**
1. Ruff 0.16.9: inline `--config` overrides apply under `--isolated` (the project's own ruff config is ignored); stdin input works and reports the absolute `--stdin-filename`; `--ignore-noqa` overrides `# noqa`, file-level `# ruff: noqa`, and `# ruff: ignore[...]`; C901 behaves the same with and without `lint.preview`. PLR1702 reports the first nested block's line, not the `def` line.
2. Vulture 2.16: line format `path:LINE: message (NN% confidence[, N lines])`, pinned by `tests/fixtures/vulture_output.txt`. A syntax error prints a non-matching line (ignored) and exits 1, or 3 if dead code was also found. A missing path or whitelist file exits 1. An invalid `--min-confidence` exits 1 with a traceback. `--make-whitelist` exits 3 when it finds items, and writes unreachable code only as a comment, so unreachable code cannot be whitelisted.
3. PMD 7.28.0 (with Java 21): exit 0/2/4/5 as documented, and the namespaced XML with absolute paths (samples in `tests/fixtures/cpd_*.xml`). `pmd --version` prints an ASCII banner before `PMD 7.28.0 (...)`. A run on a small project takes about 1 s.

**Verified:**
1. Ruff: the five config key names; PLR1702 is preview-only, and C901, PLR0913, PLR0915 and PLR0917 are stable; `--ignore-noqa` exists; exit codes 0/1/2; JSON output fields.
2. Vulture: exit codes 0/1/2/3; flags; `[tool.vulture]` keys use underscores; confidence levels; no machine-readable output.
3. PMD CPD: `pmd cpd` syntax; exit codes 0/1/2/4/5; XML schema and namespace since 7.3.0; ignore flags are Java/C++ only; Java 8+.
4. Claude Code: default hook timeout 600 s with a per-hook `timeout`; plugins can bundle `hooks/hooks.json`; hooks receive no list of changed files.
5. Claude Code hooks, by the M0 probe (2026-09-30, fixtures in `tests/fixtures/hooks/`):
   1. Project `.claude/settings.json` hooks fire live in the running session. `CLAUDE_PROJECT_DIR` is set, and the process cwd is the project root.
   2. Per-edit hooks were probed but are not used, since v1 checks only at Stop. For reference: PreToolUse exit 2 refuses the edit (file unchanged on disk), and PostToolUse exit 2 only gives feedback because the edit has already been applied.
   3. Stop stdin has `stop_hook_active`: `false` on the first stop, `true` on the retry after a blocked stop. Exit 2 prevents stopping, and stderr is shown to Claude as "Stop hook feedback".
   4. `MultiEdit` is not in the tool list of the build used for M0. Keeping it in the matcher is harmless.
   5. The JSON-output channel was not tested. Exit 2 with stderr works for all three events, so v1 uses that.

## 11. Later improvements

1. Full baseline mode across a whole session (a snapshot at session start), if `existing_violations = "allow"` proves too coarse.
2. A true line-count limit per function (lizard's NLOC is one option), if statement count proves too loose.
3. Cognitive complexity (complexipy) as an optional check.
4. `Any` in annotations: flag `dict[str, Any]` and similar in the annotations check. Ruff ANN401 flags only a bare `Any` on arguments and returns, including `*args: Any` and `**kwargs: Any`.
5. A second duplication engine (jscpd) behind the same interface, possibly one that can catch renamed copy-paste in Python.
5. Other languages.
