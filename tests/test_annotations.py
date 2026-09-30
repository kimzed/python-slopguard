from conftest import commit_all

from slopguard.checks.annotations import AnnotationComplexity
from slopguard.checks.base import Context
from slopguard.config import load_config
from slopguard.vcs import changed_files

HEADER = "from typing import Any, Annotated, List, Literal, Optional, Tuple, TypeAlias\n"


def run(repo, **edit):
    config = load_config(repo)
    config["edit"].update(edit)
    return AnnotationComplexity().run(Context(repo, config, changed_files(repo)))


def codes(repo, source, **edit):
    (repo / "mod.py").write_text(HEADER + source)
    return [finding.code for finding in run(repo, **edit)]


def test_plugin_reference_scores(repo):
    assert codes(repo, "def f(x: List[int]) -> None: ...\n") == []
    assert codes(repo, "def f() -> Tuple[List[Optional[str]], int]: ...\n") == ["annotation-depth"]


def test_depth_message_and_hint(repo):
    (repo / "mod.py").write_text(HEADER + "def f(x: list[dict[str, list[int]]]) -> None: ...\n")
    [finding] = run(repo)
    assert (finding.path, finding.line) == ("mod.py", 2)
    assert "annotation nests 4 levels (> 3)." in finding.message
    assert "not with a type alias" in finding.message


def test_modern_syntax_within_limits_passes(repo):
    source = (
        "def f(a: dict[str, list[int]] | None, b: dict[str, tuple[int, ...]]) -> None: ...\n"
        "def g(x: Annotated[list[int], 'meta']) -> Literal['a', 'b', 'c', 'd', 'e']: ...\n"
    )
    assert codes(repo, source) == []


def test_string_annotation_is_measured(repo):
    assert codes(repo, "def f() -> 'dict[str, list[tuple[int, int]]]': ...\n") == [
        "annotation-depth"
    ]


def test_too_many_types(repo):
    assert codes(
        repo, "def f(x: tuple[int, int, int, int, int, int, int, int]) -> None: ...\n"
    ) == ["annotation-size"]


def test_wide_return_tuple(repo):
    assert codes(repo, "def f() -> tuple[int, str, float, bytes]: ...\n") == ["return-tuple"]
    assert codes(repo, "async def f() -> tuple[int, str, float]: ...\n") == []
    assert codes(repo, "def f() -> tuple[int, ...]: ...\n") == []


def test_wide_tuple_argument_is_not_a_return_tuple(repo):
    assert codes(repo, "def f(x: tuple[int, str, float, bytes]) -> None: ...\n") == []


def test_annotated_assignment_and_class_field(repo):
    source = (
        "x: dict[str, list[tuple[int, int]]] = {}\nclass C:\n    field: list[list[list[int]]]\n"
    )
    assert codes(repo, source) == ["annotation-depth", "annotation-depth"]


def test_aliases_are_measured(repo):
    source = (
        "Plain = tuple[dict[str, list[int]], int]\n"
        "Explicit: TypeAlias = dict[str, list[tuple[int, int]]]\n"
        "Wide = tuple[int, str, float, bytes]\n"
    )
    assert codes(repo, source) == ["annotation-depth", "annotation-depth", "return-tuple"]


def test_type_statement_alias(repo):
    assert codes(repo, "type R = dict[str, list[tuple[int, int]]]\n") == ["annotation-depth"]


def test_plain_subscript_assignment_is_not_an_alias(repo):
    assert codes(repo, "data = [[[1]]]\nx = data[0][0][0]\ny = data[(0, 0, 0, 0)]\n") == []


def test_syntax_error_yields_no_findings(repo):
    assert codes(repo, "def f(:\n") == []


def test_limits_come_from_config(repo):
    source = "def f() -> tuple[int, str, float, bytes]: ...\n"
    assert codes(repo, source, max_return_tuple=4) == []


DEEP = "def old() -> list[list[list[int]]]: ...\n"
NEW = "def new() -> list[list[list[str]]]: ...\n"


def test_allow_mode_reports_only_new_violations(repo):
    (repo / "mod.py").write_text(DEEP)
    commit_all(repo)
    (repo / "mod.py").write_text("\n" + DEEP + NEW)
    [finding] = run(repo)
    assert finding.line == 3


def test_block_mode_reports_existing_violations(repo):
    (repo / "mod.py").write_text(DEEP)
    commit_all(repo)
    (repo / "mod.py").write_text("\n" + DEEP + NEW)
    assert len(run(repo, existing_violations="block")) == 2
