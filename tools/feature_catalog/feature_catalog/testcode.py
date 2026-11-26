"""Finds a test in its file and inspects its body (N4, N6 heuristics; the review still decides).

Python tests are read with `ast`; TypeScript tests (vitest, Playwright) by the test title and
brace counting. The inspected text includes decorators (parametrize values) and helper
functions of the same file that the test calls, directly or through other helpers.
"""

import ast
import re
import warnings
from dataclasses import dataclass, field
from pathlib import Path

STATUS_COMPARE = re.compile(r".*status_code\)?\s*(==|!=|in|<|>|<=|>=)\s*[\d\s(),\[\]{}]+")
BARE = re.compile(r"[\w.()\[\]'\"]+")


def status_only_assertion(segment: str) -> bool:
    """`assert r.status_code == 200`, `assert x is not None` or a bare truthiness check."""
    text = " ".join(segment.split())
    return bool(
        STATUS_COMPARE.fullmatch(text) or BARE.fullmatch(text) or text.endswith(" is not None")
    )


STATUS_ONLY_TS = re.compile(
    r"expect\([^)]*(status\(\)|\.ok\(\))\)\.(toBe|toEqual)\([^)]*\)"
    r"|\.toBeTruthy\(\)|\.toBeDefined\(\)|\.not\.toBeNull\(\)"
)
IMPORT_WORDS = {"import", "type", "from", "as"}
TS_ASSERT = re.compile(r"\bexpect(\.soft|\.poll)?\(|\bassert\(")


@dataclass
class TestBody:
    found: bool
    text: str = ""  # test source plus called helpers of the same file
    line: int = 0
    assertions: int = 0
    status_only: bool = False
    helpers: list[str] = field(default_factory=list)


# ---------------------------------------------------------------- Python


def _py_assert_status_only(source: str, node: ast.Assert) -> bool:
    return status_only_assertion(ast.get_source_segment(source, node.test) or "")


def _py_find(tree: ast.Module, test: str) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    cls_name, _, func_name = test.rpartition("::")
    scopes: list[ast.AST] = [tree]
    if cls_name:
        scopes = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls_name]
    for scope in scopes:
        for node in getattr(scope, "body", []):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == func_name:
                return node
    return None


def _segment(source: str, node: ast.AST) -> str:
    lines = source.splitlines()
    start = min([d.lineno for d in getattr(node, "decorator_list", [])] + [node.lineno])  # type: ignore[attr-defined]
    return "\n".join(lines[start - 1 : node.end_lineno])  # type: ignore[attr-defined]


def _module_file(path: Path, module: str) -> Path | None:
    """`tests.helpers` imported from backend/tests/test_x.py -> backend/tests/helpers.py."""
    relative = Path(*module.split(".")).with_suffix(".py")
    for parent in path.parents:
        if (parent / relative).exists():
            return parent / relative
    return None


def _imported_helpers(path: Path, tree: ast.Module, used: set[str]) -> list[str]:
    """Sources of used helper functions imported from other test modules (one level deep)."""
    texts: list[str] = []
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom) or not node.module:
            continue
        names = {a.name for a in node.names if (a.asname or a.name) in used}
        if not names or node.module.split(".")[0] not in ("tests", "test"):
            continue
        file = _module_file(path, node.module)
        if file is None:
            continue
        source = file.read_text(encoding="utf-8")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            other = ast.parse(source)
        for fn in other.body:
            if isinstance(fn, ast.FunctionDef | ast.AsyncFunctionDef) and fn.name in names:
                texts.append(_segment(source, fn))
    return texts


def python_test(path: Path, test: str) -> TestBody:
    source = path.read_text(encoding="utf-8")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)
        tree = ast.parse(source)
    node = _py_find(tree, test)
    if node is None:
        return TestBody(found=False)
    helpers = {
        n.name: n
        for n in tree.body
        if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef) and not n.name.startswith("test")
    }
    constants: dict[str, ast.stmt] = {}
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                if isinstance(target, ast.Name):
                    constants[target.id] = stmt
        elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            constants[stmt.target.id] = stmt  # `MATRIX: list[Case] = [...]`
    seen: list[str] = []
    todo: list[ast.AST] = [node]
    while todo:
        current = todo.pop()
        for call in ast.walk(current):
            if isinstance(call, ast.Name) and call.id in helpers and call.id not in seen:
                seen.append(call.id)
                todo.append(helpers[call.id])
    asserts = [n for n in ast.walk(node) if isinstance(n, ast.Assert)]
    raises = [
        n
        for n in ast.walk(node)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and (n.func.attr == "raises" or n.func.attr.startswith("assert"))
    ]
    status_only = (
        bool(asserts) and not raises and all(_py_assert_status_only(source, a) for a in asserts)
    )
    parts = [node, *(helpers[h] for h in seen)]
    # Module constants count only where the test or its helpers use them (URL prefixes).
    used = {n.id for part in parts for n in ast.walk(part) if isinstance(n, ast.Name)}
    texts = [_segment(source, part) for part in parts]
    texts += [_segment(source, constants[name]) for name in sorted(used & constants.keys())]
    # Imports of used names show which modules the test exercises (`from app.x import y`).
    texts += [
        _segment(source, n)
        for n in tree.body
        if isinstance(n, ast.ImportFrom) and {a.asname or a.name for a in n.names} & used
    ]
    texts += _imported_helpers(path, tree, used)
    return TestBody(
        found=True,
        text="\n".join(texts),
        line=node.lineno,
        assertions=len(asserts) + len(raises),
        status_only=status_only,
        helpers=seen,
    )


# ---------------------------------------------------------------- TypeScript


def _block(source: str, start: int) -> str:
    """Source from `start` to the end of the first {...} block after it."""
    depth = 0
    opened = False
    i = start
    in_str: str | None = None
    while i < len(source):
        ch = source[i]
        if in_str:
            if ch == "\\":
                i += 2
                continue
            if ch == in_str:
                in_str = None
        elif ch in "'\"`":
            in_str = ch
        elif ch == "{":
            depth += 1
            opened = True
        elif ch == "}":
            depth -= 1
            if opened and depth == 0:
                return source[start : i + 1]
        i += 1
    return source[start:]


def ts_test(path: Path, test: str) -> TestBody:
    source = path.read_text(encoding="utf-8")
    title = test.split(" > ")[-1].split(" \u203a ")[-1]
    pattern = re.compile(r"\b(it|test)(\.only)?\(\s*(['\"`])" + re.escape(title) + r"\3")
    match = pattern.search(source)
    if match is None:
        return TestBody(found=False)
    # The body is the block after the callback's arrow (or `function`), not the braces of
    # destructured fixtures such as `async ({ page }) => {`.
    arrow = re.compile(r"=>\s*\{|function\s*\([^)]*\)\s*\{").search(source, match.end())
    body_start = arrow.end() - 1 if arrow else match.start()
    body = source[match.start() : body_start] + _block(source, body_start)
    helper_names = set(re.findall(r"(?:async\s+)?function\s+(\w+)\s*\(", source))
    helper_names |= set(re.findall(r"const\s+(\w+)\s*=\s*(?:async\s*)?\(", source))
    seen: list[str] = []
    todo = [body]
    texts = [body]
    while todo:
        current = todo.pop()
        for name in helper_names:
            if name not in seen and re.search(rf"\b{name}\(", current):
                seen.append(name)
                helper = re.search(
                    rf"(?:async\s+)?function\s+{name}\s*\(|const\s+{name}\s*=", source
                )
                if helper:
                    block = _block(source, helper.start())
                    texts.append(block)
                    todo.append(block)
    # Top-level constants the test uses (`const O = `/orgs/${ORG_ID}`;`).
    for name, value in re.findall(r"^const\s+(\w+)\s*=\s*([^;]*);", source, re.M):
        if re.search(rf"\b{re.escape(name)}\b", "\n".join(texts)):
            texts.append(f"const {name} = {value};")
    # Imports of names the test uses show which modules it exercises.
    joined = "\n".join(texts)
    for line in re.findall(r"^import\s+[^;]+?from\s+['\"][^'\"]+['\"];?$", source, re.M):
        names = re.findall(r"\b\w+\b", line.split("from")[0])
        if any(re.search(rf"\b{re.escape(n)}\b", joined) for n in names if n not in IMPORT_WORDS):
            texts.append(line)
    assertions = len(TS_ASSERT.findall(body))
    status = len(STATUS_ONLY_TS.findall(body))
    return TestBody(
        found=True,
        text="\n".join(texts),
        line=source.count("\n", 0, match.start()) + 1,
        assertions=assertions,
        status_only=assertions > 0 and status >= assertions,
        helpers=seen,
    )


def inspect_test(path: Path, test: str) -> TestBody:
    if not path.exists():
        return TestBody(found=False)
    if path.suffix == ".py":
        return python_test(path, test)
    return ts_test(path, test)
