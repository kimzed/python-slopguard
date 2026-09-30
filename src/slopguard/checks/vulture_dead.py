"""Dead code across the project via vulture."""

import re
import subprocess
import sys

from slopguard.checks.base import Context, ToolError
from slopguard.report import Finding

# e.g. "src/app.py:6: unused function 'helper' (60% confidence)"
LINE = re.compile(r"^(.+?):(\d+): (.+) \((\d+)% confidence(?:, \d+ lines?)?\)$")
DEAD_CODE_FOUND = 3


class VultureDead:
    name = "dead_code"

    def run(self, ctx: Context) -> list[Finding]:
        command = _command(ctx)
        if command is None:
            return []
        result = subprocess.run(
            command, cwd=ctx.project_dir, capture_output=True, text=True, check=False
        )
        if result.returncode not in (0, DEAD_CODE_FOUND):
            # The last line holds the actual error, even after a traceback.
            output = (result.stderr or result.stdout).strip().splitlines() or [""]
            raise ToolError(f"vulture exited {result.returncode}: {output[-1]}")
        return _parse(result.stdout)


def _command(ctx: Context) -> list[str] | None:
    cfg = ctx.config["dead_code"]
    paths = [path for path in cfg["paths"] if (ctx.project_dir / path).exists()]
    if not paths:
        return None
    command = [sys.executable, "-m", "vulture", *paths]
    if (ctx.project_dir / cfg["whitelist"]).is_file():
        command.append(cfg["whitelist"])
    command += ["--min-confidence", str(cfg["min_confidence"])]
    options = {
        "--exclude": ctx.config["exclude"],
        "--ignore-decorators": cfg["ignore_decorators"],
        "--ignore-names": cfg["ignore_names"],
    }
    for flag, values in options.items():
        if values:
            command += [flag, ",".join(values)]
    return command


def _parse(stdout: str) -> list[Finding]:
    findings = []
    for line in stdout.splitlines():
        match = LINE.match(line)
        if match:
            path, row, message, _confidence = match.groups()
            findings.append(Finding(path, int(row), "dead-code", message))
    return findings
