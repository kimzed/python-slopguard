from conftest import commit_all

from slopguard.checks.base import Context
from slopguard.checks.file_length import FileLength
from slopguard.config import load_config
from slopguard.vcs import changed_files


def run(repo, **edit):
    config = load_config(repo)
    config["edit"].update({"max_file_lines": 10, **edit})
    return FileLength().run(Context(repo, config, changed_files(repo)))


def write_lines(path, count):
    path.write_text("".join(f"x{i} = {i}\n" for i in range(count)))


def test_long_file_is_reported(repo):
    write_lines(repo / "big.py", 11)
    [finding] = run(repo)
    assert (finding.path, finding.code) == ("big.py", "file-length")
    assert "11 lines (> 10)" in finding.message


def test_file_at_limit_passes(repo):
    write_lines(repo / "ok.py", 10)
    assert run(repo) == []


def test_allow_mode_lets_legacy_long_file_shrink_or_stay(repo):
    write_lines(repo / "legacy.py", 20)
    commit_all(repo)
    write_lines(repo / "legacy.py", 19)
    assert run(repo) == []


def test_allow_mode_reports_legacy_long_file_that_grows(repo):
    write_lines(repo / "legacy.py", 20)
    commit_all(repo)
    write_lines(repo / "legacy.py", 21)
    assert len(run(repo)) == 1


def test_block_mode_reports_legacy_long_file(repo):
    write_lines(repo / "legacy.py", 20)
    commit_all(repo)
    write_lines(repo / "legacy.py", 19)
    assert len(run(repo, existing_violations="block")) == 1
