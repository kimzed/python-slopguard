"""Copy-paste duplication via PMD CPD."""

import os
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import NamedTuple

from slopguard.checks.base import Context, MissingToolError, ToolError, is_excluded
from slopguard.report import Finding

PMD_VERSION = "7.28.0"
PMD_DOWNLOAD = (
    "https://github.com/pmd/pmd/releases/download/"
    f"pmd_releases/{PMD_VERSION}/pmd-dist-{PMD_VERSION}-bin.zip"
)
# 0 = no duplication, 4 = duplication found, 5 = recoverable errors (e.g. lexical).
PARSEABLE_EXIT_CODES = (0, 4, 5)
NAMESPACE = "{https://pmd-code.org/schema/cpd-report}"


class Location(NamedTuple):
    path: str  # relative to the project
    line: int


class PmdCpd:
    name = "duplication"

    def run(self, ctx: Context) -> list[Finding]:
        cfg = ctx.config["duplication"]
        paths = [path for path in cfg["paths"] if (ctx.project_dir / path).exists()]
        if not paths:
            return []
        pmd = shutil.which("pmd")
        if pmd is None:
            raise MissingToolError(
                f"pmd not found on PATH; install PMD {PMD_VERSION} from {PMD_DOWNLOAD}"
            )
        command = [
            pmd,
            "cpd",
            "--language",
            "python",
            "--format",
            "xml",
            "--minimum-tokens",
            str(cfg["min_tokens"]),
        ]
        for path in paths:
            command += ["--dir", path]
        result = subprocess.run(
            command, cwd=ctx.project_dir, capture_output=True, text=True, check=False
        )
        if result.returncode not in PARSEABLE_EXIT_CODES:
            output = (result.stderr or result.stdout).strip().splitlines() or [""]
            raise ToolError(f"pmd cpd exited {result.returncode}: {output[-1]}")
        return report(parse(result.stdout, ctx.project_dir), ctx)


def parse(xml_text: str, project_dir: Path) -> list[list[Location]]:
    """Locations of each duplicated block.

    Handles both report shapes: PMD 7.3+ uses a namespace, older versions do not.
    """
    root = ET.fromstring(xml_text)
    blocks = []
    for duplication in _children(root, "duplication"):
        locations: list[Location] = []
        for location in _children(duplication, "file"):
            path = Path(os.path.relpath(location.get("path", ""), project_dir)).as_posix()
            entry = Location(path, int(location.get("line", "0")))
            if entry not in locations:  # older PMD versions repeated locations
                locations.append(entry)
        blocks.append(locations)
    return blocks


def report(blocks: list[list[Location]], ctx: Context) -> list[Finding]:
    cfg = ctx.config["duplication"]
    patterns = ctx.config["exclude"] + cfg["exclude"]
    findings = []
    for block in blocks:
        locations = [loc for loc in block if not is_excluded(loc.path, patterns)]
        if len(locations) < cfg["min_occurrences"]:
            continue
        touched = [loc for loc in locations if ctx.changed is None or loc.path in ctx.changed]
        if not touched:
            continue  # old duplication that this change did not add to
        where = ", ".join(f"{path}:{line}" for path, line in locations)
        message = (
            f"block duplicated {len(locations)} times ({where}). "
            "Extract it into one shared function."
        )
        findings.append(Finding(touched[0].path, touched[0].line, "duplication", message))
    return findings


def _children(element: ET.Element, tag: str) -> list[ET.Element]:
    return element.findall(f"{NAMESPACE}{tag}") or element.findall(tag)
