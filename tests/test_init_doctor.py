import json

import pytest
from conftest import commit_all, copy_fixture, stop_input

from slopguard import doctor
from slopguard.cli import main
from slopguard.config import DEFAULTS, load_config
from slopguard.hooks import run_stop
from slopguard.init import HOOK_COMMAND, init_project

USER_SOUND_HOOK = {
    "hooks": {
        "Stop": [{"hooks": [{"type": "command", "command": "paplay complete.oga || true"}]}],
        "Notification": [{"hooks": [{"type": "command", "command": "paplay message.oga"}]}],
    },
    "model": "opus",
}


def settings(repo):
    return json.loads((repo / ".claude" / "settings.json").read_text())


def test_init_on_empty_project(repo):
    init_project(repo)
    assert load_config(repo) == DEFAULTS
    [group] = settings(repo)["hooks"]["Stop"]
    assert group["hooks"] == [{"type": "command", "command": HOOK_COMMAND, "timeout": 120}]


def test_init_preserves_existing_hooks_and_settings(repo):
    (repo / ".claude").mkdir()
    (repo / ".claude" / "settings.json").write_text(json.dumps(USER_SOUND_HOOK))
    init_project(repo)
    result = settings(repo)
    assert result["model"] == "opus"
    assert result["hooks"]["Notification"] == USER_SOUND_HOOK["hooks"]["Notification"]
    stop_commands = [
        hook["command"] for group in result["hooks"]["Stop"] for hook in group["hooks"]
    ]
    assert stop_commands == ["paplay complete.oga || true", HOOK_COMMAND]


def test_init_is_idempotent(repo):
    init_project(repo)
    first = (repo / "pyproject.toml").read_text(), settings(repo)
    actions = init_project(repo)
    assert ((repo / "pyproject.toml").read_text(), settings(repo)) == first
    config_action, whitelist_action, hook_action = actions
    assert config_action.startswith("kept existing")
    assert whitelist_action == "no dead_code paths exist yet; whitelist not generated"
    assert hook_action.startswith("kept existing")


def test_init_keeps_existing_config_and_other_tables(repo):
    original = '[project]\nname = "demo"\n\n[tool.slopguard.edit]\nmax_complexity = 9\n'
    (repo / "pyproject.toml").write_text(original)
    init_project(repo)
    assert (repo / "pyproject.toml").read_text() == original


def test_init_appends_config_after_other_tables(repo):
    (repo / "pyproject.toml").write_text('[project]\nname = "demo"')
    init_project(repo)
    text = (repo / "pyproject.toml").read_text()
    assert text.startswith('[project]\nname = "demo"\n')
    assert load_config(repo) == DEFAULTS


def test_init_whitelist_makes_existing_dead_code_pass(repo):
    copy_fixture("dead.py", repo, "src/app.py")
    commit_all(repo)
    (repo / "src" / "app.py").write_text((repo / "src" / "app.py").read_text() + "\n")
    assert run_stop(stop_input(repo)).exit_code == 2
    actions = init_project(repo)
    assert "wrote vulture_whitelist.py exempting 2 existing dead-code item(s)" in actions
    assert run_stop(stop_input(repo)).exit_code == 0


def test_init_refuses_invalid_settings_json(repo, monkeypatch, capsys):
    (repo / ".claude").mkdir()
    (repo / ".claude" / "settings.json").write_text("{not json")
    monkeypatch.chdir(repo)
    assert main(["init"]) == 1
    assert "init failed" in capsys.readouterr().err
    assert (repo / ".claude" / "settings.json").read_text() == "{not json"


def test_doctor_reports_missing_java(monkeypatch):
    real_which = doctor.shutil.which
    monkeypatch.setattr(
        doctor.shutil, "which", lambda name: None if name == "java" else real_which(name)
    )
    ok, lines = doctor.run_doctor()
    assert not ok
    assert "FAIL java: java not found on PATH; PMD needs a Java 8+ runtime" in lines


def test_doctor_reports_missing_pmd_with_pinned_download(monkeypatch):
    monkeypatch.setattr(
        doctor.shutil, "which", lambda name: None if name == "pmd" else "/usr/bin/" + name
    )
    _, lines = doctor.run_doctor()
    [pmd_line] = [line for line in lines if "pmd" in line.split(":")[0]]
    assert pmd_line.startswith(
        "FAIL pmd: pmd not found on PATH; install PMD 7.28.0 from https://github.com/pmd/pmd/releases/download/pmd_releases/7.28.0/"
    )


@pytest.mark.parametrize(
    ("banner", "ok"), [("PMD 7.28.0 (abc)", True), ("PMD 7.27.1 (abc)", False)]
)
def test_doctor_enforces_pmd_pin(monkeypatch, banner, ok):
    monkeypatch.setattr(doctor.shutil, "which", lambda name: "/usr/bin/pmd")
    monkeypatch.setattr(
        doctor, "_output", lambda command: f"  ascii art\n{banner}\nJava version: 21"
    )
    _, _, problem = doctor._pmd()
    assert (problem is None) == ok
    if not ok:
        assert "found PMD 7.27.1, slopguard is pinned to 7.28.0" in problem


def test_doctor_reports_pinned_python_tools():
    _, lines = doctor.run_doctor()
    assert "ok   ruff: ruff 0.16.9" in lines
    assert "ok   vulture: vulture 2.16" in lines
