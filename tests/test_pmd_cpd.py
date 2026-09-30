import shutil
from pathlib import Path

import pytest
from conftest import FIXTURES, commit_all, copy_fixture, stop_input

from slopguard.checks import pmd_cpd
from slopguard.checks.base import Context, MissingToolError
from slopguard.checks.pmd_cpd import Location, PmdCpd, parse, report
from slopguard.config import load_config
from slopguard.hooks import run_stop
from slopguard.vcs import changed_files

PROJECT = Path("/project")
THREE_COPIES = [Location("src/a.py", 1), Location("src/b.py", 1), Location("src/c.py", 1)]
needs_pmd = pytest.mark.skipif(shutil.which("pmd") is None, reason="PMD not on PATH")


def ctx(changed, **duplication):
    config = load_config(Path("/nonexistent"))
    config["duplication"].update(duplication)
    return Context(PROJECT, config, changed)


def test_parses_namespaced_report():
    assert parse((FIXTURES / "cpd_7_28.xml").read_text(), PROJECT) == [THREE_COPIES]


def test_parses_legacy_report_and_dedupes_locations():
    assert parse((FIXTURES / "cpd_legacy.xml").read_text(), PROJECT) == [THREE_COPIES]


def test_parses_report_with_recoverable_errors():
    blocks = parse((FIXTURES / "cpd_7_28_error.xml").read_text(), PROJECT)
    assert blocks == [THREE_COPIES]


def test_three_copies_involving_a_changed_file_are_reported():
    [finding] = report([THREE_COPIES], ctx(["src/b.py"]))
    assert (finding.path, finding.line, finding.code) == ("src/b.py", 1, "duplication")
    assert "duplicated 3 times (src/a.py:1, src/b.py:1, src/c.py:1)" in finding.message


def test_two_copies_are_not_reported():
    assert report([THREE_COPIES[:2]], ctx(["src/a.py"])) == []


def test_min_occurrences_is_configurable():
    assert len(report([THREE_COPIES[:2]], ctx(["src/a.py"], min_occurrences=2))) == 1


def test_old_duplication_is_not_reported():
    assert report([THREE_COPIES], ctx(["src/other.py"])) == []


def test_everything_is_reported_outside_git():
    assert len(report([THREE_COPIES], ctx(None))) == 1


def test_excluded_locations_do_not_count():
    assert report([THREE_COPIES], ctx(["src/a.py"], exclude=["src/c.py"])) == []


def test_missing_pmd_follows_on_missing_tool(repo, monkeypatch):
    copy_fixture("dup_block.py", repo, "src/a.py")
    monkeypatch.setattr(pmd_cpd.shutil, "which", lambda name: None)
    with pytest.raises(MissingToolError, match="install PMD 7.28.0"):
        PmdCpd().run(Context(repo, load_config(repo), changed_files(repo)))
    monkeypatch.setattr("slopguard.checks.vulture_dead.VultureDead.run", lambda self, ctx: [])
    outcome = run_stop(stop_input(repo))
    assert (outcome.exit_code, "duplication skipped: pmd not found" in outcome.stderr) == (0, True)
    (repo / "pyproject.toml").write_text('[tool.slopguard]\non_missing_tool = "error"\n')
    assert run_stop(stop_input(repo)).exit_code == 2
    (repo / "pyproject.toml").write_text('[tool.slopguard]\non_missing_tool = "skip"\n')
    assert run_stop(stop_input(repo)).stderr == ""


@needs_pmd
def test_real_pmd_flags_three_copies(repo):
    for name in ("a", "b"):
        copy_fixture("dup_block.py", repo, f"src/{name}.py")
    commit_all(repo)
    copy_fixture("dup_block.py", repo, "src/c.py")
    findings = PmdCpd().run(Context(repo, load_config(repo), changed_files(repo)))
    assert [(f.path, f.code) for f in findings] == [("src/c.py", "duplication")]


@needs_pmd
def test_real_pmd_ignores_two_copies(repo):
    for name in ("a", "b"):
        copy_fixture("dup_block.py", repo, f"src/{name}.py")
    assert PmdCpd().run(Context(repo, load_config(repo), changed_files(repo))) == []
