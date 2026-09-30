import subprocess
import sys

from conftest import copy_fixture, stop_input

from slopguard import hooks
from slopguard.checks import ruff_limits
from slopguard.hooks import run_stop


def test_slop_blocks_stop_with_readable_report(repo):
    copy_fixture("slop.py", repo, "app/slop.py")
    outcome = run_stop(stop_input(repo))
    assert outcome.exit_code == 2
    assert "slopguard: 4 problem(s) must be fixed before you finish:" in outcome.stderr
    assert "app/slop.py:1: C901 `tangled` is too complex" in outcome.stderr
    assert outcome.stderr.endswith("Fix by refactoring. Do not add suppression comments.")


def test_clean_change_allows_stop(repo):
    copy_fixture("clean.py", repo, "app/clean.py")
    assert run_stop(stop_input(repo)).exit_code == 0


def test_no_python_change_exits_without_running_checks(repo, monkeypatch):
    (repo / "README.md").write_text("changed\n")
    monkeypatch.setattr(hooks, "_run_checks", lambda *a: (_ for _ in ()).throw(AssertionError))
    assert run_stop(stop_input(repo)).exit_code == 0


def test_retry_after_block_does_not_block_again(repo):
    copy_fixture("slop.py", repo, "app/slop.py")
    outcome = run_stop(stop_input(repo, retry=True))
    assert outcome.exit_code == 0
    assert "not blocking again" in outcome.stderr
    assert "C901" in outcome.stderr


def test_report_is_capped(repo):
    copy_fixture("slop.py", repo, "app/slop.py")
    (repo / "pyproject.toml").write_text("[tool.slopguard]\nmax_findings = 1\n")
    outcome = run_stop(stop_input(repo))
    assert "...and 3 more" in outcome.stderr
    assert outcome.stderr.count("app/slop.py:") == 1


def test_disabled_edit_checks(repo):
    copy_fixture("slop.py", repo, "app/slop.py")
    (repo / "pyproject.toml").write_text("[tool.slopguard.edit]\nenabled = false\n")
    assert run_stop(stop_input(repo)).exit_code == 0


def test_tool_error_is_a_warning_not_a_finding(repo, monkeypatch):
    copy_fixture("slop.py", repo, "app/slop.py")
    monkeypatch.setattr(
        ruff_limits, "_command", lambda ctx: ["sh", "-c", "echo boom >&2; exit 2", "-"]
    )
    outcome = run_stop(stop_input(repo))
    assert outcome.exit_code == 0
    assert "ruff_limits failed, not blocking: ruff exited 2: boom" in outcome.stderr


def test_config_error_does_not_block(repo):
    copy_fixture("slop.py", repo, "app/slop.py")
    (repo / "pyproject.toml").write_text("[tool.slopguard]\nbogus = 1\n")
    outcome = run_stop(stop_input(repo))
    assert outcome.exit_code == 0
    assert "config error" in outcome.stderr


def test_outside_git_repo_skips_changed_file_limits(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    copy_fixture("slop.py", tmp_path, "slop.py")
    outcome = run_stop(stop_input(tmp_path))
    assert outcome.exit_code == 0
    assert "not a git repo" in outcome.stderr


def test_cli_entry_point_end_to_end(repo):
    copy_fixture("slop.py", repo, "app/slop.py")
    result = subprocess.run(
        [sys.executable, "-m", "slopguard.cli", "hook", "stop"],
        input=stop_input(repo),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "C901" in result.stderr
