from conftest import commit_all, copy_fixture

from slopguard.checks.base import Context
from slopguard.checks.ruff_limits import RuffLimits
from slopguard.config import DEFAULTS, load_config
from slopguard.vcs import changed_files

NEW_FUNCTION = """

def added(a, b, c, d, e):
    return a
"""


def run(repo, **edit):
    config = load_config(repo)
    config["edit"].update(edit)
    return RuffLimits().run(Context(repo, config, changed_files(repo)))


def codes(findings):
    return sorted(finding.code for finding in findings)


def test_slop_fixture_triggers_every_rule(repo):
    copy_fixture("slop.py", repo, "src/slop.py")
    findings = run(repo)
    assert codes(findings) == ["C901", "PLR0913", "PLR0917", "PLR1702"]
    assert {finding.path for finding in findings} == {"src/slop.py"}


def test_statement_limit(repo):
    body = "".join(f"    x{i} = {i}\n" for i in range(30))
    (repo / "long.py").write_text(f"def f():\n{body}")
    assert codes(run(repo)) == ["PLR0915"]


def test_clean_fixture_passes(repo):
    copy_fixture("clean.py", repo, "src/clean.py")
    assert run(repo) == []


def test_limits_come_from_config(repo):
    copy_fixture("slop.py", repo, "src/slop.py")
    assert (
        run(repo, max_complexity=50, max_args=10, max_positional_args=10, max_nested_blocks=10)
        == []
    )


def test_noqa_is_ignored_unless_respected(repo):
    (repo / "a.py").write_text("def f(a, b, c, d, e):  # noqa: PLR0913, PLR0917\n    return a\n")
    assert codes(run(repo)) == ["PLR0913", "PLR0917"]
    (repo / "pyproject.toml").write_text("[tool.slopguard]\nrespect_noqa = true\n")
    assert run(repo) == []


def test_excluded_and_non_python_files_are_skipped(repo):
    copy_fixture("slop.py", repo, "migrations/slop.py")
    copy_fixture("slop.py", repo, "notes/slop.txt")
    (repo / "pyproject.toml").write_text('[tool.slopguard]\nexclude = ["migrations/*"]\n')
    assert run(repo) == []


def test_allow_mode_ignores_existing_violations(repo):
    copy_fixture("slop.py", repo, "src/slop.py")
    commit_all(repo)
    path = repo / "src/slop.py"
    path.write_text("import os\n\n" + path.read_text())  # shifts every line
    assert run(repo) == []


def test_allow_mode_reports_only_new_violations(repo):
    copy_fixture("slop.py", repo, "src/slop.py")
    commit_all(repo)
    with (repo / "src/slop.py").open("a") as fh:
        fh.write(NEW_FUNCTION)
    findings = run(repo)
    assert codes(findings) == ["PLR0913", "PLR0917"]
    assert all(finding.line == 19 for finding in findings)


def test_block_mode_reports_existing_violations(repo):
    copy_fixture("slop.py", repo, "src/slop.py")
    commit_all(repo)
    with (repo / "src/slop.py").open("a") as fh:
        fh.write("\n")
    assert codes(run(repo, existing_violations="block")) == [
        "C901",
        "PLR0913",
        "PLR0917",
        "PLR1702",
    ]


def test_defaults_match_plan():
    edit = DEFAULTS["edit"]
    assert (
        edit["max_complexity"],
        edit["max_args"],
        edit["max_statements"],
        edit["max_nested_blocks"],
    ) == (6, 4, 25, 3)
