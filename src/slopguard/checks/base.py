"""The interface every check implements."""

from collections import Counter
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path
from typing import Any, Protocol

from slopguard.report import Finding

# A violation is identified by its rule and the text of the flagged line, which
# survives line shifts between the committed and current versions of a file.
Key = tuple[str, str]


class ToolError(Exception):
    """An external tool failed; never reported to Claude as a finding."""


class MissingToolError(ToolError):
    """An external tool is not installed."""


@dataclass(frozen=True)
class Context:
    project_dir: Path
    config: dict[str, Any]
    # Relative paths of changed files, or None outside a git repo.
    changed: list[str] | None


class Check(Protocol):
    name: str

    def run(self, ctx: Context) -> list[Finding]: ...


def is_excluded(path: str, patterns: list[str]) -> bool:
    return any(fnmatch(path, pattern) for pattern in patterns)


def edit_targets(ctx: Context) -> list[str]:
    """Changed Python files subject to the `[edit]` limits."""
    patterns = ctx.config["exclude"] + ctx.config["edit"]["exclude"]
    return [
        path
        for path in ctx.changed or []
        if path.endswith(".py") and not is_excluded(path, patterns)
    ]


def new_only(after: list[tuple[Finding, Key]], before: list[tuple[Finding, Key]]) -> list[Finding]:
    """Findings in `after` that were not already present in `before`."""
    remaining = Counter(key for _, key in before)
    new = []
    for finding, key in after:
        if remaining[key]:
            remaining[key] -= 1
        else:
            new.append(finding)
    return new
