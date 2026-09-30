"""`slopguard doctor`: check that every external tool is installed and pinned."""

import os
import re
import shutil
import subprocess
import sys

from ruff import find_ruff_bin

from slopguard.checks.pmd_cpd import PMD_DOWNLOAD, PMD_VERSION


def run_doctor() -> tuple[bool, list[str]]:
    """Return (all ok, one report line per tool)."""
    results = [
        ("ruff", _first_line([os.fsdecode(find_ruff_bin()), "--version"]), None),
        ("vulture", _first_line([sys.executable, "-m", "vulture", "--version"]), None),
        _java(),
        _pmd(),
    ]
    lines = []
    ok = True
    for name, version, problem in results:
        if problem:
            ok = False
            lines.append(f"FAIL {name}: {problem}")
        else:
            lines.append(f"ok   {name}: {version}")
    return ok, lines


def _java() -> tuple[str, str | None, str | None]:
    java = shutil.which("java")
    if java is None:
        return "java", None, "java not found on PATH; PMD needs a Java 8+ runtime"
    return "java", _first_line([java, "-version"]), None


def _pmd() -> tuple[str, str | None, str | None]:
    hint = f"install PMD {PMD_VERSION} from {PMD_DOWNLOAD} and put its bin/ on PATH"
    pmd = shutil.which("pmd")
    if pmd is None:
        return "pmd", None, f"pmd not found on PATH; {hint}"
    output = _output([pmd, "--version"])
    match = re.search(r"^PMD (\S+)", output, re.MULTILINE)
    found = match.group(1) if match else "unknown"
    if found != PMD_VERSION:
        return "pmd", found, f"found PMD {found}, slopguard is pinned to {PMD_VERSION}; {hint}"
    return "pmd", found, None


def _first_line(command: list[str]) -> str:
    lines = _output(command).splitlines()
    return lines[0] if lines else "unknown"


def _output(command: list[str]) -> str:
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    # java prints its version to stderr.
    return (result.stdout + result.stderr).strip()
