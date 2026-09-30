"""Nesting, size, and tuple limits for type annotations and aliases (no ruff rule covers these)."""

import ast
from collections.abc import Iterator

from slopguard import vcs
from slopguard.checks.base import Context, Key, edit_targets, new_only
from slopguard.report import Finding

HINT = (
    "Replace nested tuples/dicts with a dataclass, NamedTuple, TypedDict or Pydantic model"
    " with named fields, not with a type alias."
)
GENERICS = {"tuple", "dict", "list", "set", "frozenset", "type"}
TYPE_ALIAS = getattr(ast, "TypeAlias", ())  # the `type X = ...` statement, Python 3.12+


class AnnotationComplexity:
    name = "annotations"

    def run(self, ctx: Context) -> list[Finding]:
        edit = ctx.config["edit"]
        findings = []
        for path in edit_targets(ctx):
            text = (ctx.project_dir / path).read_text(encoding="utf-8", errors="replace")
            after = _analyze(path, text, edit)
            if edit["existing_violations"] == "block":
                findings += [finding for finding, _ in after]
            else:
                before = _analyze(path, vcs.committed_content(ctx.project_dir, path), edit)
                findings += new_only(after, before)
        return findings


def _analyze(path: str, text: str, edit: dict) -> list[tuple[Finding, Key]]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []  # syntax errors are not slop findings
    lines = text.splitlines()
    results = []
    for node, check_tuples in _annotations(tree):
        line_text = lines[node.lineno - 1].strip() if node.lineno <= len(lines) else ""
        for code, message in _violations(node, check_tuples, edit):
            finding = Finding(path, node.lineno, code, f"{message} {HINT}")
            results.append((finding, (code, line_text)))
    return sorted(results, key=lambda result: result[0].line)


def _annotations(tree: ast.Module) -> Iterator[tuple[ast.expr, bool]]:
    """Each annotation or alias value, and whether its tuple sizes are limited."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield from _signature(node)
        elif isinstance(node, ast.AnnAssign):
            yield _annotated_assignment(node)
        elif isinstance(node, TYPE_ALIAS):
            yield node.value, True
    yield from ((node.value, True) for node in tree.body if _is_plain_alias(node))


def _signature(function: ast.FunctionDef | ast.AsyncFunctionDef) -> Iterator[tuple[ast.expr, bool]]:
    args = function.args
    params = [*args.posonlyargs, *args.args, args.vararg, *args.kwonlyargs, args.kwarg]
    for param in params:
        if param is not None and param.annotation is not None:
            yield param.annotation, False
    if function.returns is not None:
        yield function.returns, True


def _annotated_assignment(node: ast.AnnAssign) -> tuple[ast.expr, bool]:
    if _head(node.annotation) == "TypeAlias" and node.value is not None:
        return node.value, True
    return node.annotation, False


def _is_plain_alias(node: ast.stmt) -> bool:
    return (
        isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and _looks_like_type(node.value)
    )


def _looks_like_type(node: ast.expr) -> bool:
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return _looks_like_type(node.left) or _looks_like_type(node.right)
    if not isinstance(node, ast.Subscript):
        return False
    head = _head(node.value) or ""
    return head in GENERICS or head[:1].isupper()


def _violations(node: ast.expr, check_tuples: bool, edit: dict) -> list[tuple[str, str]]:
    found = []
    depth, size = _depth(node), _size(node)
    if depth > edit["max_annotation_depth"]:
        limit = edit["max_annotation_depth"]
        found.append(("annotation-depth", f"annotation nests {depth} levels (> {limit})."))
    if size > edit["max_annotation_elements"]:
        limit = edit["max_annotation_elements"]
        found.append(("annotation-size", f"annotation has {size} types (> {limit})."))
    widest = _widest_tuple(node) if check_tuples else 0
    if widest > edit["max_return_tuple"]:
        limit = edit["max_return_tuple"]
        message = f"tuple of {widest} elements in a return type or alias (> {limit})."
        found.append(("return-tuple", message))
    return found


def _depth(node: ast.expr) -> int:
    """`List[int]` is 2 and `Tuple[List[Optional[str]], int]` is 4; `X | None` adds no level."""
    node = _resolve(node)
    return _level(node) + max((_depth(child) for child in _children(node)), default=0)


def _size(node: ast.expr) -> int:
    """The number of leaf types, not counting generic heads like `dict`."""
    node = _resolve(node)
    children = _children(node)
    if not children:
        return _level(node)
    return sum(_size(child) for child in children)


def _widest_tuple(node: ast.expr) -> int:
    node = _resolve(node)
    children = _children(node)
    own = 0
    if isinstance(node, ast.Subscript) and _head(node.value) in ("tuple", "Tuple"):
        own = 0 if any(_is_ellipsis(child) for child in children) else len(children)
    return max([own, *(_widest_tuple(child) for child in children)])


def _level(node: ast.expr) -> int:
    """1 for a type or generic; 0 for unions, `Callable` parameter lists, `...`, `Annotated`."""
    if isinstance(node, (ast.BinOp, ast.List)) or _is_ellipsis(node):
        return 0
    return 0 if isinstance(node, ast.Subscript) and _head(node.value) == "Annotated" else 1


def _children(node: ast.expr) -> list[ast.expr]:
    if isinstance(node, ast.BinOp):
        return [node.left, node.right]
    if isinstance(node, ast.List):
        return node.elts
    if isinstance(node, ast.Subscript):
        return _type_args(node)
    return []


def _type_args(node: ast.Subscript) -> list[ast.expr]:
    head = _head(node.value)
    if head == "Literal":
        return []
    args = node.slice.elts if isinstance(node.slice, ast.Tuple) else [node.slice]
    return args[:1] if head == "Annotated" else args


def _resolve(node: ast.expr) -> ast.expr:
    """Parse a string (forward-reference) annotation into an expression."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        try:
            return ast.parse(node.value, mode="eval").body
        except SyntaxError:
            return node
    return node


def _head(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _is_ellipsis(node: ast.expr) -> bool:
    return isinstance(node, ast.Constant) and node.value is Ellipsis
