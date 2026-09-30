"""Load `[tool.slopguard]` from pyproject.toml, merge with defaults, validate."""

import copy
import tomllib
from pathlib import Path
from typing import Any

DEFAULTS: dict[str, Any] = {
    "exclude": [],
    "respect_noqa": False,
    "max_findings": 10,
    "on_missing_tool": "warn",
    "feedback_footer": "Fix by refactoring. Do not add suppression comments.",
    "edit": {
        "enabled": True,
        "max_complexity": 6,
        "max_args": 4,
        "max_positional_args": 4,
        "max_statements": 25,
        "max_nested_blocks": 3,
        "max_file_lines": 400,
        "max_annotation_depth": 3,
        "max_annotation_elements": 7,
        "max_return_tuple": 3,
        "existing_violations": "allow",
        "exclude": [],
    },
    "dead_code": {
        "enabled": True,
        "paths": ["src"],
        "min_confidence": 60,
        "ignore_decorators": [],
        "ignore_names": [],
        "whitelist": "vulture_whitelist.py",
    },
    "duplication": {
        "enabled": True,
        "paths": ["src", "tests"],
        "min_tokens": 70,
        "min_occurrences": 3,
        "exclude": [],
    },
}

CHOICES: dict[str, tuple[str, ...]] = {
    "on_missing_tool": ("warn", "skip", "error"),
    "edit.existing_violations": ("allow", "block"),
}


class ConfigError(Exception):
    """Invalid slopguard configuration."""


def load_config(project_dir: Path) -> dict[str, Any]:
    """Return the effective config for the project rooted at `project_dir`."""
    user = _read_table(project_dir / "pyproject.toml")
    return _merge(DEFAULTS, user, prefix="")


def _read_table(pyproject: Path) -> dict[str, Any]:
    if not pyproject.is_file():
        return {}
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{pyproject}: invalid TOML: {exc}") from exc
    return data.get("tool", {}).get("slopguard", {})


def _merge(defaults: dict[str, Any], user: dict[str, Any], prefix: str) -> dict[str, Any]:
    merged = copy.deepcopy(defaults)
    for key, value in user.items():
        name = f"{prefix}{key}"
        if key not in defaults:
            raise ConfigError(f"unknown key [tool.slopguard] {name!r}")
        default = defaults[key]
        if isinstance(default, dict):
            if not isinstance(value, dict):
                raise ConfigError(f"{name!r} must be a table")
            merged[key] = _merge(default, value, prefix=f"{name}.")
            continue
        merged[key] = _check_value(name, value, default)
    return merged


def _check_value(name: str, value: Any, default: Any) -> Any:
    # `type(...) is` so that `true` is not accepted where an integer is expected.
    if type(value) is not type(default):
        expected = type(default).__name__
        raise ConfigError(f"{name!r} must be {expected}, got {type(value).__name__}")
    if isinstance(value, list) and not all(isinstance(item, str) for item in value):
        raise ConfigError(f"{name!r} must be a list of strings")
    choices = CHOICES.get(name)
    if choices and value not in choices:
        raise ConfigError(f"{name!r} must be one of {', '.join(choices)}; got {value!r}")
    return value
