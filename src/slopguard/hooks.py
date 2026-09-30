"""The Claude Code Stop hook: exit 2 keeps Claude from finishing."""

import json
import os
from dataclasses import dataclass
from pathlib import Path

from slopguard import vcs
from slopguard.checks.annotations import AnnotationComplexity
from slopguard.checks.base import Check, Context, MissingToolError, ToolError
from slopguard.checks.file_length import FileLength
from slopguard.checks.pmd_cpd import PmdCpd
from slopguard.checks.ruff_limits import RuffLimits
from slopguard.checks.vulture_dead import VultureDead
from slopguard.config import ConfigError, load_config
from slopguard.report import Finding, format_report

ALLOW = 0
BLOCK = 2


@dataclass
class Outcome:
    exit_code: int
    stderr: str


def run_stop(stdin_text: str) -> Outcome:
    payload = json.loads(stdin_text or "{}")
    project_dir = Path(os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or ".")
    try:
        config = load_config(project_dir)
    except ConfigError as exc:
        return Outcome(ALLOW, f"slopguard: config error, checks skipped: {exc}")

    changed = vcs.changed_files(project_dir)
    if changed is not None and not any(path.endswith(".py") for path in changed):
        return Outcome(ALLOW, "")
    ctx = Context(project_dir, config, changed)
    findings, warnings = _run_checks(ctx, _enabled_checks(config))
    if changed is None:
        warnings.append("slopguard: not a git repo, limits on changed files were skipped")

    if not findings:
        return Outcome(ALLOW, "\n".join(warnings))
    report = format_report(findings, config)
    if payload.get("stop_hook_active"):
        # One fix attempt was already made; do not trap Claude in a loop.
        note = "slopguard: still failing after one attempt, not blocking again."
        return Outcome(ALLOW, "\n".join([*warnings, note, report]))
    return Outcome(BLOCK, "\n".join([*warnings, report]))


def _enabled_checks(config: dict) -> list[Check]:
    checks: list[Check] = []
    if config["edit"]["enabled"]:
        checks += [RuffLimits(), FileLength(), AnnotationComplexity()]
    if config["dead_code"]["enabled"]:
        checks.append(VultureDead())
    if config["duplication"]["enabled"]:
        checks.append(PmdCpd())
    return checks


def _run_checks(ctx: Context, checks: list[Check]) -> tuple[list[Finding], list[str]]:
    findings: list[Finding] = []
    warnings: list[str] = []
    for check in checks:
        try:
            findings += check.run(ctx)
        except MissingToolError as exc:
            policy = ctx.config["on_missing_tool"]
            if policy == "error":
                findings.append(Finding("-", 0, "missing-tool", str(exc)))
            elif policy == "warn":
                warnings.append(f"slopguard: {check.name} skipped: {exc}")
        except ToolError as exc:
            warnings.append(f"slopguard: {check.name} failed, not blocking: {exc}")
    return findings, warnings
