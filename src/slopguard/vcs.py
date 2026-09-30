"""Changed files and committed content, via git."""

import subprocess
from pathlib import Path


def changed_files(project_dir: Path) -> list[str] | None:
    """Relative paths of modified or untracked files that still exist.

    Returns None when `project_dir` is not inside a git work tree.
    """
    result = _git(project_dir, "status", "--porcelain", "-z", "--untracked-files=all")
    if result.returncode != 0:
        return None
    entries = result.stdout.split("\0")
    paths = []
    index = 0
    while index < len(entries):
        entry = entries[index]
        index += 1
        if not entry:
            continue
        status, path = entry[:2], entry[3:]
        if "R" in status or "C" in status:
            index += 1  # the next field is the original path of a rename or copy
        if (project_dir / path).is_file():
            paths.append(path)
    return paths


def committed_content(project_dir: Path, path: str) -> str:
    """Content of `path` at HEAD, or "" if it is not committed."""
    result = _git(project_dir, "show", f"HEAD:{path}")
    return result.stdout if result.returncode == 0 else ""


def _git(project_dir: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=project_dir,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
