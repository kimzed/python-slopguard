"""Complexity, argument, statement, and nesting limits via ruff."""

import json
import os
import subprocess
import tempfile
from pathlib import Path

from ruff import find_ruff_bin

from slopguard import vcs
from slopguard.checks.base import Context, Key, ToolError, edit_targets, new_only
from slopguard.report import Finding

RULES = "C901,PLR0913,PLR0915,PLR1702,PLR0917"
LIMITS = {
    "lint.mccabe.max-complexity": "max_complexity",
    "lint.pylint.max-args": "max_args",
    "lint.pylint.max-positional-args": "max_positional_args",
    "lint.pylint.max-statements": "max_statements",
    "lint.pylint.max-nested-blocks": "max_nested_blocks",
}


class RuffLimits:
    name = "ruff_limits"

    def run(self, ctx: Context) -> list[Finding]:
        targets = edit_targets(ctx)
        if not targets:
            return []
        after = _lint(ctx, ctx.project_dir, targets)
        if ctx.config["edit"]["existing_violations"] == "block":
            return [finding for finding, _ in after]
        return new_only(after, _lint_committed(ctx, targets))


def _lint_committed(ctx: Context, targets: list[str]) -> list[tuple[Finding, Key]]:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        committed = []
        for path in targets:
            content = vcs.committed_content(ctx.project_dir, path)
            if content:
                (root / path).parent.mkdir(parents=True, exist_ok=True)
                (root / path).write_text(content, encoding="utf-8")
                committed.append(path)
        return _lint(ctx, root, committed) if committed else []


def _lint(ctx: Context, root: Path, paths: list[str]) -> list[tuple[Finding, Key]]:
    result = subprocess.run(
        _command(ctx) + paths, cwd=root, capture_output=True, text=True, check=False
    )
    if result.returncode not in (0, 1):
        raise ToolError(f"ruff exited {result.returncode}: {result.stderr.strip()}")
    results = []
    for item in json.loads(result.stdout or "[]"):
        if not item.get("code") or not item.get("location") or not item.get("filename"):
            continue  # syntax errors and similar are not slop findings
        path = Path(os.path.relpath(item["filename"], root)).as_posix()
        row = item["location"]["row"]
        finding = Finding(path, row, item["code"], item["message"])
        results.append((finding, (item["code"], _line_text(root / path, row))))
    return results


def _command(ctx: Context) -> list[str]:
    edit = ctx.config["edit"]
    command = [
        os.fsdecode(find_ruff_bin()),
        "check",
        "--isolated",
        "--no-fix",
        "--output-format",
        "json",
        "--select",
        RULES,
        "--config",
        "lint.preview = true",
        "--config",
        "lint.explicit-preview-rules = true",
    ]
    for key, setting in LIMITS.items():
        command += ["--config", f"{key} = {edit[setting]}"]
    if not ctx.config["respect_noqa"]:
        command.append("--ignore-noqa")
    return command


def _line_text(path: Path, row: int) -> str:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return lines[row - 1].strip() if 0 < row <= len(lines) else ""
