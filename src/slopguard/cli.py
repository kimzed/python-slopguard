"""Command-line entry point."""

import argparse
import json
import sys
from pathlib import Path

from slopguard.config import ConfigError, load_config
from slopguard.doctor import run_doctor
from slopguard.hooks import run_stop
from slopguard.init import init_project


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="slopguard")
    commands = parser.add_subparsers(dest="command", required=True)
    config_parser = commands.add_parser("config", help="inspect configuration")
    config_commands = config_parser.add_subparsers(dest="config_command", required=True)
    config_commands.add_parser("show", help="print the effective config as JSON")
    hook_parser = commands.add_parser("hook", help="Claude Code hook entry points")
    hook_commands = hook_parser.add_subparsers(dest="hook_command", required=True)
    hook_commands.add_parser("stop", help="Stop hook: reads hook JSON on stdin")
    commands.add_parser("init", help="set up slopguard in the current project")
    commands.add_parser("doctor", help="check that ruff, vulture, Java, and PMD are ready")
    args = parser.parse_args(argv)

    if args.command == "config":
        return _config_show(Path.cwd())
    if args.command == "init":
        return _init()
    if args.command == "doctor":
        return _doctor()
    return _hook_stop()


def _init() -> int:
    try:
        actions = init_project(Path.cwd())
    except (ConfigError, ValueError) as exc:  # ValueError: invalid TOML or JSON
        print(f"slopguard: init failed, nothing further changed: {exc}", file=sys.stderr)
        return 1
    print("\n".join(actions))
    return 0


def _doctor() -> int:
    ok, lines = run_doctor()
    print("\n".join(lines))
    return 0 if ok else 1


def _hook_stop() -> int:
    outcome = run_stop(sys.stdin.read())
    if outcome.stderr:
        print(outcome.stderr, file=sys.stderr)
    return outcome.exit_code


def _config_show(project_dir: Path) -> int:
    try:
        config = load_config(project_dir)
    except ConfigError as exc:
        print(f"slopguard: config error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(config, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
