import json
import shutil
import subprocess
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def commit_all(repo: Path) -> None:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "snapshot")


def copy_fixture(name: str, repo: Path, dest: str) -> Path:
    target = repo / dest
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(FIXTURES / name, target)
    return target


def stop_input(repo: Path, retry: bool = False) -> str:
    """Real Stop hook JSON captured by the M0 probe, pointed at `repo`."""
    name = "stop_retry.json" if retry else "stop_first.json"
    payload = json.loads((FIXTURES / "hooks" / name).read_text())
    payload["cwd"] = str(repo)
    return json.dumps(payload)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "test@example.com")
    git(tmp_path, "config", "user.name", "test")
    git(tmp_path, "config", "commit.gpgsign", "false")
    (tmp_path / "README.md").write_text("fixture repo\n")
    commit_all(tmp_path)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    return tmp_path
