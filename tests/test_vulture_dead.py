import subprocess
import sys

from conftest import FIXTURES, copy_fixture, stop_input

from slopguard.checks.base import Context
from slopguard.checks.vulture_dead import VultureDead, _parse
from slopguard.config import load_config
from slopguard.hooks import run_stop
from slopguard.vcs import changed_files


def run(repo, **dead_code):
    config = load_config(repo)
    config["dead_code"].update(dead_code)
    return VultureDead().run(Context(repo, config, changed_files(repo)))


def names(findings):
    return sorted(finding.message for finding in findings)


def test_parses_real_vulture_output_and_skips_other_lines():
    findings = _parse((FIXTURES / "vulture_output.txt").read_text())
    assert len(findings) == 7
    assert findings[4].path == "src/app.py"
    assert findings[4].line == 6
    assert findings[4].message == "unused function 'unused_helper'"


def test_parses_output_without_size_suffix():
    [finding] = _parse("src/a.py:3: unused class 'Foo' (60% confidence)\n")
    assert (finding.path, finding.line, finding.code) == ("src/a.py", 3, "dead-code")


def test_unused_function_is_flagged(repo):
    copy_fixture("dead.py", repo, "src/app.py")
    assert names(run(repo)) == ["unused function 'handler'", "unused function 'unused_helper'"]


def test_decorator_ignored_function_is_not_flagged(repo):
    copy_fixture("dead.py", repo, "src/app.py")
    assert names(run(repo, ignore_decorators=["@route"])) == ["unused function 'unused_helper'"]


def test_whitelisted_function_is_not_flagged(repo):
    copy_fixture("dead.py", repo, "src/app.py")
    (repo / "vulture_whitelist.py").write_text("unused_helper\nhandler\n")
    assert run(repo) == []


def test_generated_whitelist_exempts_existing_dead_code(repo):
    copy_fixture("dead.py", repo, "src/app.py")
    whitelist = subprocess.run(
        [sys.executable, "-m", "vulture", "src", "--make-whitelist"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    (repo / "vulture_whitelist.py").write_text(whitelist)
    assert run(repo) == []


def test_missing_paths_are_skipped(repo):
    assert run(repo, paths=["does_not_exist"]) == []


def test_excluded_paths_are_skipped(repo):
    copy_fixture("dead.py", repo, "src/generated/app.py")
    (repo / "pyproject.toml").write_text('[tool.slopguard]\nexclude = ["*/generated/*"]\n')
    assert run(repo) == []


def test_tool_error_is_not_a_finding(repo):
    copy_fixture("dead.py", repo, "src/app.py")
    (repo / "pyproject.toml").write_text("[tool.slopguard.dead_code]\nmin_confidence = 900\n")
    outcome = run_stop(stop_input(repo))
    assert outcome.exit_code == 0
    assert (
        "dead_code failed, not blocking: vulture exited 1: ValueError: min_confidence must be between 0 and 100."
        in outcome.stderr
    )


def test_dead_code_blocks_stop(repo):
    copy_fixture("dead.py", repo, "src/app.py")
    outcome = run_stop(stop_input(repo))
    assert outcome.exit_code == 2
    assert "src/app.py:5: dead-code unused function 'unused_helper'" in outcome.stderr
