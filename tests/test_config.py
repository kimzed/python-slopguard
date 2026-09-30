import json
import textwrap

import pytest

from slopguard.cli import main
from slopguard.config import DEFAULTS, ConfigError, load_config


def write_pyproject(tmp_path, body):
    (tmp_path / "pyproject.toml").write_text(textwrap.dedent(body))


def test_defaults_without_pyproject(tmp_path):
    assert load_config(tmp_path) == DEFAULTS


def test_defaults_without_slopguard_table(tmp_path):
    write_pyproject(tmp_path, '[project]\nname = "x"\n')
    assert load_config(tmp_path) == DEFAULTS


def test_user_values_override_defaults_per_key(tmp_path):
    write_pyproject(
        tmp_path,
        """
        [tool.slopguard]
        max_findings = 3

        [tool.slopguard.edit]
        max_complexity = 8
        existing_violations = "block"
        """,
    )
    config = load_config(tmp_path)
    assert config["max_findings"] == 3
    assert config["edit"]["max_complexity"] == 8
    assert config["edit"]["existing_violations"] == "block"
    assert config["edit"]["max_args"] == DEFAULTS["edit"]["max_args"]
    assert config["dead_code"] == DEFAULTS["dead_code"]


def test_defaults_are_not_mutated(tmp_path):
    write_pyproject(tmp_path, '[tool.slopguard.edit]\nexclude = ["tests/**"]\n')
    load_config(tmp_path)
    assert DEFAULTS["edit"]["exclude"] == []


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("[tool.slopguard]\nmax_findngs = 3\n", "unknown key [tool.slopguard] 'max_findngs'"),
        (
            "[tool.slopguard.edit]\nmax_complexty = 3\n",
            "unknown key [tool.slopguard] 'edit.max_complexty'",
        ),
        ("[tool.slopguard.nope]\nx = 1\n", "unknown key [tool.slopguard] 'nope'"),
        ("[tool.slopguard]\nedit = 3\n", "'edit' must be a table"),
        ("[tool.slopguard.edit]\nmax_args = true\n", "'edit.max_args' must be int, got bool"),
        ('[tool.slopguard.edit]\nmax_args = "4"\n', "'edit.max_args' must be int, got str"),
        ("[tool.slopguard]\nexclude = [1]\n", "'exclude' must be a list of strings"),
        (
            '[tool.slopguard]\non_missing_tool = "ignore"\n',
            "'on_missing_tool' must be one of warn, skip, error",
        ),
        (
            '[tool.slopguard.edit]\nexisting_violations = "new"\n',
            "'edit.existing_violations' must be one of allow, block",
        ),
    ],
)
def test_invalid_config_is_an_error(tmp_path, body, message):
    write_pyproject(tmp_path, body)
    with pytest.raises(ConfigError, match=message.replace("[", r"\[").replace("]", r"\]")):
        load_config(tmp_path)


def test_invalid_toml_is_an_error(tmp_path):
    write_pyproject(tmp_path, "[tool.slopguard\n")
    with pytest.raises(ConfigError, match="invalid TOML"):
        load_config(tmp_path)


def test_config_show_prints_effective_config(tmp_path, monkeypatch, capsys):
    write_pyproject(tmp_path, "[tool.slopguard.edit]\nmax_complexity = 9\n")
    monkeypatch.chdir(tmp_path)
    assert main(["config", "show"]) == 0
    assert json.loads(capsys.readouterr().out)["edit"]["max_complexity"] == 9


def test_config_show_reports_errors(tmp_path, monkeypatch, capsys):
    write_pyproject(tmp_path, "[tool.slopguard]\nbogus = 1\n")
    monkeypatch.chdir(tmp_path)
    assert main(["config", "show"]) == 1
    assert "config error: unknown key" in capsys.readouterr().err
