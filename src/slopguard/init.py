"""`slopguard init`: wire slopguard into a project without overwriting anything."""

import json
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

from slopguard.config import DEFAULTS, load_config

HOOK_COMMAND = "slopguard hook stop"
# PMD starts a JVM; leave room for large projects.
HOOK_TIMEOUT_SECONDS = 120


def init_project(project_dir: Path) -> list[str]:
    """Run every init step and return one line per action taken."""
    return [
        _add_config(project_dir / "pyproject.toml"),
        _generate_whitelist(project_dir),
        _add_stop_hook(project_dir / ".claude" / "settings.json"),
    ]


def _add_config(pyproject: Path) -> str:
    text = pyproject.read_text(encoding="utf-8") if pyproject.is_file() else ""
    if "slopguard" in tomllib.loads(text).get("tool", {}):
        return f"kept existing [tool.slopguard] in {pyproject.name}"
    separator = "\n" if text and not text.endswith("\n") else ""
    pyproject.write_text(text + separator + _starter_table(), encoding="utf-8")
    return f"added [tool.slopguard] to {pyproject.name}"


def _starter_table() -> str:
    lines = ["", "[tool.slopguard]"]
    sections = {key: value for key, value in DEFAULTS.items() if isinstance(value, dict)}
    lines += [f"{key} = {_toml(value)}" for key, value in DEFAULTS.items() if key not in sections]
    for name, section in sections.items():
        lines += ["", f"[tool.slopguard.{name}]"]
        lines += [f"{key} = {_toml(value)}" for key, value in section.items()]
    return "\n".join(lines) + "\n"


def _toml(value: Any) -> str:
    # Config values are only bools, ints, strings, and lists of strings; for
    # those, JSON spelling is valid TOML.
    return json.dumps(value)


def _generate_whitelist(project_dir: Path) -> str:
    cfg = load_config(project_dir)["dead_code"]
    whitelist = project_dir / cfg["whitelist"]
    if whitelist.exists():
        return f"kept existing {cfg['whitelist']}"
    paths = [path for path in cfg["paths"] if (project_dir / path).exists()]
    if not paths:
        return "no dead_code paths exist yet; whitelist not generated"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "vulture",
            *paths,
            "--make-whitelist",
            "--min-confidence",
            str(cfg["min_confidence"]),
        ],
        cwd=project_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode not in (0, 3):
        error = (result.stderr or result.stdout).strip().splitlines() or [""]
        return f"whitelist not generated, vulture exited {result.returncode}: {error[-1]}"
    whitelist.write_text(result.stdout, encoding="utf-8")
    count = sum(1 for line in result.stdout.splitlines() if not line.startswith("#"))
    return f"wrote {cfg['whitelist']} exempting {count} existing dead-code item(s)"


def _add_stop_hook(settings_path: Path) -> str:
    settings = (
        json.loads(settings_path.read_text(encoding="utf-8")) if settings_path.is_file() else {}
    )
    stop_groups = settings.setdefault("hooks", {}).setdefault("Stop", [])
    commands = [hook.get("command", "") for group in stop_groups for hook in group.get("hooks", [])]
    if any(HOOK_COMMAND in command for command in commands):
        return f"kept existing slopguard Stop hook in {settings_path}"
    hook = {"type": "command", "command": HOOK_COMMAND, "timeout": HOOK_TIMEOUT_SECONDS}
    stop_groups.append({"hooks": [hook]})
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    return f"added slopguard Stop hook to {settings_path}"
