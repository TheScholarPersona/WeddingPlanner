"""Which endpoint does a test call? A heuristic for the ENDPOINT_UNTESTED warning.

A path only counts when a method comes right with it: `client.post("/x")`,
`send(client, "POST", url)`, `request.get(`...`)`. Python URL expressions are resolved through
f-strings, module constants, local variables and helper functions of the same or an imported
test module (`MB(world, wedding, "/items")`); anything unknown becomes `{}`.
"""

import ast
import re
import warnings
from pathlib import Path

METHODS = {"get", "post", "put", "patch", "delete"}
TS_CALL = re.compile(r"\.(get|post|put|patch|delete)\(\s*[`'\"](/[^`'\"]*)[`'\"]", re.IGNORECASE)
UNKNOWN = "{}"


class _Module:
    def __init__(self, path: Path, resolver: "PythonCalls") -> None:
        self.path = path
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            self.tree = ast.parse(path.read_text(encoding="utf-8"))
        self.resolver = resolver
        self.constants: dict[str, ast.expr] = {}
        self.functions: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
        self.imports: dict[str, tuple[str, str]] = {}
        for node in self.tree.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                target = node.targets[0]
                if isinstance(target, ast.Name):
                    self.constants[target.id] = node.value
            elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                self.functions[node.name] = node
            elif isinstance(node, ast.ImportFrom) and node.module:
                for alias in node.names:
                    self.imports[alias.asname or alias.name] = (node.module, alias.name)

    def function(
        self, name: str
    ) -> "tuple[_Module, ast.FunctionDef | ast.AsyncFunctionDef] | None":
        if name in self.functions:
            return self, self.functions[name]
        if name in self.imports:
            module, original = self.imports[name]
            other = self.resolver.module(module)
            if other is not None:
                return other.function(original)
        return None


class PythonCalls:
    def __init__(self, root: Path) -> None:
        self.root = root  # directory the test modules are importable from (backend/)
        self._modules: dict[str, _Module | None] = {}

    def module(self, dotted: str) -> _Module | None:
        if dotted not in self._modules:
            path = self.root / (dotted.replace(".", "/") + ".py")
            self._modules[dotted] = _Module(path, self) if path.exists() else None
        return self._modules[dotted]

    def _render(
        self, module: _Module, expr: ast.expr | None, scope: dict[str, ast.expr], depth: int = 0
    ) -> str:
        if expr is None or depth > 8:
            return UNKNOWN
        if isinstance(expr, ast.Constant) and isinstance(expr.value, str):
            return expr.value
        if isinstance(expr, ast.JoinedStr):
            return "".join(
                self._render(
                    module, v.value if isinstance(v, ast.FormattedValue) else v, scope, depth + 1
                )
                for v in expr.values
            )
        if isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.Add):
            return self._render(module, expr.left, scope, depth + 1) + self._render(
                module, expr.right, scope, depth + 1
            )
        if isinstance(expr, ast.Name):
            if expr.id in scope:
                return self._render(module, scope[expr.id], {}, depth + 1)
            if expr.id in module.constants:
                return self._render(module, module.constants[expr.id], {}, depth + 1)
            return UNKNOWN
        if isinstance(expr, ast.Call) and isinstance(expr.func, ast.Name):
            found = module.function(expr.func.id)
            if found is None:
                return UNKNOWN
            other, func = found
            returns = [n.value for n in ast.walk(func) if isinstance(n, ast.Return)]
            if len(returns) != 1:
                return UNKNOWN
            params = [a.arg for a in func.args.args]
            defaults = dict(
                zip(
                    params[len(params) - len(func.args.defaults) :], func.args.defaults, strict=True
                )
            )
            inner: dict[str, ast.expr] = {}
            for name, arg in zip(params, expr.args, strict=False):
                inner[name] = _Bound(self._render(module, arg, scope, depth + 1))
            for kw in expr.keywords:
                if kw.arg:
                    inner[kw.arg] = _Bound(self._render(module, kw.value, scope, depth + 1))
            for name, default in defaults.items():
                inner.setdefault(name, default)
            return self._render(other, returns[0], inner, depth + 1)
        if isinstance(expr, _Bound):
            return expr.text
        return UNKNOWN

    def _bind(
        self,
        module: _Module,
        call: ast.Call,
        func: ast.FunctionDef | ast.AsyncFunctionDef,
        scope: dict[str, ast.expr],
    ) -> dict[str, ast.expr]:
        params = [a.arg for a in func.args.args]
        bound: dict[str, ast.expr] = {}
        for name, arg in zip(params, call.args, strict=False):
            bound[name] = _Bound(self._render(module, arg, scope))
        for kw in call.keywords:
            if kw.arg:
                bound[kw.arg] = _Bound(self._render(module, kw.value, scope))
        return bound

    def _scan(
        self,
        module: _Module,
        func: ast.FunctionDef | ast.AsyncFunctionDef,
        bound: dict[str, ast.expr],
        result: list[tuple[str, str]],
        depth: int = 0,
    ) -> None:
        scope = dict(bound)
        for node in ast.walk(func):
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                target = node.targets[0]
                if isinstance(target, ast.Name) and target.id not in bound:
                    scope[target.id] = node.value
        for node in ast.walk(func):
            if not isinstance(node, ast.Call):
                continue
            method: str | None = None
            url: ast.expr | None = None
            if isinstance(node.func, ast.Attribute) and node.func.attr in METHODS and node.args:
                method, url = node.func.attr.upper(), node.args[0]
            elif (
                len(node.args) >= 3
                and isinstance(node.args[1], ast.Constant)
                and isinstance(node.args[1].value, str)
                and node.args[1].value.lower() in METHODS
            ):
                method, url = node.args[1].value.upper(), node.args[2]
            if method and url is not None:
                rendered = self._render(module, url, scope)
                if rendered.startswith("/"):
                    result.append((method, normalize(rendered)))
            elif isinstance(node.func, ast.Name) and depth < 3:
                # A helper of this or an imported test module that sends requests itself.
                found = module.function(node.func.id)
                if found is not None and found[1] is not func:
                    other, helper = found
                    self._scan(
                        other, helper, self._bind(module, node, helper, scope), result, depth + 1
                    )

    def calls(self, path: Path) -> list[tuple[str, str]]:
        dotted = path.resolve().relative_to(self.root.resolve()).with_suffix("").as_posix()
        module = self.module(dotted.replace("/", "."))
        if module is None:
            return []
        result: list[tuple[str, str]] = []
        for func in module.tree.body:
            if isinstance(func, ast.FunctionDef | ast.AsyncFunctionDef) and func.name.startswith(
                "test"
            ):
                self._scan(module, func, {}, result)
            elif isinstance(func, ast.ClassDef):
                for inner in func.body:
                    if isinstance(
                        inner, ast.FunctionDef | ast.AsyncFunctionDef
                    ) and inner.name.startswith("test"):
                        self._scan(module, inner, {}, result)
        return result


class _Bound(ast.expr):
    """An argument already rendered at the call site."""

    def __init__(self, text: str) -> None:
        super().__init__()
        self.text = text


def normalize(path: str) -> str:
    path = path.split("?", 1)[0]
    path = re.sub(r"\$\{[^}]*\}|\{[^}]*\}", UNKNOWN, path)
    return path.rstrip("/") or "/"


def ts_calls(path: Path) -> list[tuple[str, str]]:
    source = path.read_text(encoding="utf-8")
    return [(m.upper(), normalize(u)) for m, u in TS_CALL.findall(source)]


def pattern(endpoint_path: str) -> re.Pattern[str]:
    """`/orgs/{org_id}/x` matches `/orgs/{}/x`, and a concrete id in its place."""
    parts = re.split(r"\{[^}]*\}", endpoint_path)
    return re.compile(
        "".join(re.escape(p) + ("[^/]+" if i < len(parts) - 1 else "") for i, p in enumerate(parts))
        + "$"
    )
