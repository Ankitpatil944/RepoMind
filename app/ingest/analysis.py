"""Static analysis on top of tree-sitter: imports, calls and HTTP endpoints.

Heuristic and name-based on purpose (no type resolution). Supported:
  Python     Flask / FastAPI style decorators, FastAPI `Depends(...)`
  JavaScript Express-style `app.get(path, ...middleware, handler)` and `router.use(...)`
  TypeScript the same, plus NestJS `@Controller` / `@Get` / `@UseGuards` decorators
"""

import ast
from collections.abc import Iterator
from dataclasses import dataclass, field

from tree_sitter import Node

from app.ingest.parser import JS_FAMILY, parse_tree

# Callee names that suggest authentication / authorization work. Written with
# only constructs common to Python `re` and Postgres `~*` so one pattern is
# used for both.
AUTH_CALL_PATTERN = (
    "(jwt|bcrypt|passlib|argon2|authenticat|authoriz|verify_?token|verify_?password|"
    "check_?password|login_?user|current_?user|decode_?token|oauth|passport)"
)


@dataclass(frozen=True)
class Call:
    callee_name: str  # last segment: "decode" for jwt.decode
    callee_full: str  # as written: "jwt.decode"
    line: int


@dataclass(frozen=True)
class RawEndpoint:
    method: str
    path: str
    framework: str
    line: int
    handler_name: str | None
    handler_line: int | None  # Python: line of the decorated handler chunk
    signals: tuple[str, ...]  # decorators / middleware / Depends(...) on the route
    inline_calls: tuple[str, ...]  # calls made by an inline (anonymous) handler


@dataclass
class Analysis:
    imports: list[str] = field(default_factory=list)
    calls: list[Call] = field(default_factory=list)
    endpoints: list[RawEndpoint] = field(default_factory=list)


def _txt(node: Node) -> str:
    return node.text.decode("utf-8", errors="replace")


def _walk(node: Node, skip: frozenset[str] = frozenset()) -> Iterator[Node]:
    """Pre-order walk; nodes whose type is in `skip` are yielded but not entered."""
    stack = [node]
    while stack:
        n = stack.pop()
        yield n
        if n is not node and n.type in skip:
            continue
        stack.extend(reversed(n.children))


def _dedupe(items) -> list:
    return list(dict.fromkeys(items))


# --------------------------------------------------------------------- Python

_PY_ROUTE_ATTRS = {"route", "api_route", "websocket", "get", "post", "put", "delete", "patch", "head", "options"}
_PY_DEPENDS = {"Depends", "Security", "fastapi.Depends", "fastapi.Security"}


def _py_string(node: Node | None) -> str | None:
    if node is None or node.type != "string":
        return None
    try:
        value = ast.literal_eval(_txt(node))
    except (ValueError, SyntaxError):
        return None
    return value if isinstance(value, str) else None


def _py_target(call: Node) -> str | None:
    fn = call.child_by_field_name("function")
    if fn is None or fn.type not in ("identifier", "attribute"):
        return None
    text = _txt(fn)
    # `conn.execute(sql).fetchall` is a call on a call's result: the text embeds
    # the inner call, so it is not a stable name. The inner call is recorded on its own.
    if "(" in text or "\n" in text or len(text) > 120:
        return None
    return text


def _py_args(call: Node) -> tuple[list[Node], dict[str, Node]]:
    args = call.child_by_field_name("arguments")
    positional: list[Node] = []
    keywords: dict[str, Node] = {}
    for a in args.named_children if args else []:
        if a.type == "keyword_argument":
            name, value = a.child_by_field_name("name"), a.child_by_field_name("value")
            if name is not None and value is not None:
                keywords[_txt(name)] = value
        elif a.type != "comment":
            positional.append(a)
    return positional, keywords


def _py_route(call: Node, target: str) -> list[tuple[str, str]] | None:
    if "." not in target:
        return None
    attr = target.rsplit(".", 1)[-1]
    if attr not in _PY_ROUTE_ATTRS:
        return None
    positional, keywords = _py_args(call)
    path = _py_string(positional[0]) if positional else _py_string(keywords.get("path"))
    if path is None or not path.startswith("/"):
        return None
    if attr in ("route", "api_route"):
        node = keywords.get("methods")
        methods = [
            s.upper()
            for s in (_py_string(c) for c in (node.named_children if node is not None else []))
            if s
        ] or ["GET"]
    elif attr == "websocket":
        methods = ["WEBSOCKET"]
    else:
        methods = [attr.upper()]
    return [(m, path) for m in methods]


def _py_depends(node: Node) -> list[str]:
    out = []
    for n in _walk(node):
        if n.type == "call" and _py_target(n) in _PY_DEPENDS:
            positional, _ = _py_args(n)
            out.append(f"Depends({_txt(positional[0])[:80] if positional else ''})")
    return out


def _py_depends_refs(node: Node) -> list[tuple[str, int]]:
    """`Depends(get_current_user)` -> ("get_current_user", line).

    FastAPI wires auth guards by *reference*, not by calling them, so without
    this the guard behind a protected route never shows up in the call graph."""
    out = []
    for n in _walk(node):
        if n.type == "call" and _py_target(n) in _PY_DEPENDS:
            positional, _ = _py_args(n)
            if positional and positional[0].type in ("identifier", "attribute"):
                text = _txt(positional[0])
                if "(" not in text:
                    out.append((text, n.start_point.row + 1))
    return out


def _py_framework(imports: list[str], target_attr: str) -> str:
    modules = {i.split(".")[0].lstrip(".") for i in imports}
    if "fastapi" in modules:
        return "fastapi"
    if "flask" in modules:
        return "flask"
    if "starlette" in modules:
        return "starlette"
    return "flask" if target_attr == "route" else "fastapi"


def _analyze_python(root: Node) -> Analysis:
    result = Analysis()

    for n in _walk(root, skip=frozenset({"decorator"})):
        if n.type == "import_statement":
            for c in n.named_children:
                name = c.child_by_field_name("name") if c.type == "aliased_import" else c
                if name is not None and name.type == "dotted_name":
                    result.imports.append(_txt(name))
        elif n.type == "import_from_statement":
            module = n.child_by_field_name("module_name")
            if module is not None:
                base = _txt(module)
                result.imports.append(base)
                # `from app.routes import auth` may import a *module*, so also
                # record `app.routes.auth`; the module graph resolves whichever exists.
                joiner = "" if base.endswith(".") else "."
                for c in n.named_children:
                    if c == module:
                        continue
                    name = c.child_by_field_name("name") if c.type == "aliased_import" else c
                    if name is not None and name.type == "dotted_name":
                        result.imports.append(f"{base}{joiner}{_txt(name)}")
        elif n.type == "call":
            target = _py_target(n)
            if target:
                result.calls.append(Call(target.rsplit(".", 1)[-1], target, n.start_point.row + 1))
    result.imports = _dedupe(result.imports)

    # router = APIRouter(prefix="/orders") / Blueprint(..., url_prefix="/x") in this file
    prefixes: dict[str, str] = {}
    router_signals: dict[str, list[str]] = {}  # APIRouter(dependencies=[Depends(...)])
    for n in _walk(root):
        if n.type != "assignment":
            continue
        left, right = n.child_by_field_name("left"), n.child_by_field_name("right")
        if left is None or left.type != "identifier" or right is None or right.type != "call":
            continue
        target = _py_target(right)
        if target and target.rsplit(".", 1)[-1] in ("APIRouter", "Blueprint"):
            _, keywords = _py_args(right)
            prefix = _py_string(keywords.get("prefix")) or _py_string(keywords.get("url_prefix"))
            if prefix:
                prefixes[_txt(left)] = prefix
            router_signals[_txt(left)] = _py_depends(right)
            for text, line in _py_depends_refs(right):
                result.calls.append(Call(text.rsplit(".", 1)[-1], text, line))

    for n in _walk(root):
        if n.type != "decorated_definition":
            continue
        definition = n.child_by_field_name("definition")
        name = definition.child_by_field_name("name") if definition is not None else None
        if definition is None or definition.type != "function_definition" or name is None:
            continue

        routes: list[tuple[str, str, str, str]] = []  # method, full path, attr, router var
        signals: list[str] = []
        for dec in (c for c in n.children if c.type == "decorator"):
            expr = next((c for c in dec.named_children if c.type != "comment"), None)
            if expr is None:
                continue
            if expr.type == "call":
                target = _py_target(expr)
            else:
                target = _txt(expr) if expr.type in ("identifier", "attribute") else None
            signals.extend(_py_depends(dec))
            for text, line in _py_depends_refs(dec):
                result.calls.append(Call(text.rsplit(".", 1)[-1], text, line))
            found = _py_route(expr, target) if expr.type == "call" and target else None
            if found:
                obj, _, attr = target.rpartition(".")
                prefix = prefixes.get(obj, "")
                routes.extend(
                    (m, prefix if (prefix and p == "/") else prefix + p, attr, obj)
                    for m, p in found
                )
            elif target:
                signals.append(target)

        params = definition.child_by_field_name("parameters")
        if params is not None:
            signals.extend(_py_depends(params))
            for text, line in _py_depends_refs(params):
                result.calls.append(Call(text.rsplit(".", 1)[-1], text, line))

        for method, path, attr, obj in routes:
            result.endpoints.append(
                RawEndpoint(
                    method=method,
                    path=path,
                    framework=_py_framework(result.imports, attr),
                    line=n.start_point.row + 1,
                    handler_name=_txt(name),
                    handler_line=n.start_point.row + 1,
                    signals=tuple(_dedupe(signals + router_signals.get(obj, []))),
                    inline_calls=(),
                )
            )
    return result


# ----------------------------------------------------------------- JavaScript

_JS_VERBS = {"get", "post", "put", "delete", "patch", "head", "options", "all"}
_JS_NAMEABLE = ("identifier", "member_expression")


def _js_string(node: Node | None) -> str | None:
    if node is None:
        return None
    text = _txt(node)
    if node.type == "string":
        return text[1:-1]
    if node.type == "template_string" and "${" not in text:
        return text[1:-1]
    return None


def _js_names(nodes: list[Node]) -> list[str]:
    out: list[str] = []
    for n in nodes:
        if n.type == "array":
            out.extend(_js_names(n.named_children))
        elif n.type in _JS_NAMEABLE:
            out.append(_txt(n))
        elif n.type == "call_expression":
            fn = n.child_by_field_name("function")
            if fn is not None and fn.type in _JS_NAMEABLE:
                out.append(_txt(fn))
    return out


def _js_calls(root: Node) -> list[Call]:
    calls = []
    for n in _walk(root):
        if n.type != "call_expression":
            continue
        fn = n.child_by_field_name("function")
        if fn is None or fn.type not in _JS_NAMEABLE:
            continue
        full = _txt(fn)
        name = full.rsplit(".", 1)[-1]
        if "(" in full or len(full) > 120 or name == "require":
            continue
        calls.append(Call(name, full, n.start_point.row + 1))
    return calls


def _analyze_javascript(root: Node) -> Analysis:
    result = Analysis(calls=_js_calls(root))

    routes = []  # (object, method, path, rest_args, line)
    uses = []  # (object, prefix, names, line)

    for n in _walk(root):
        if n.type == "import_statement":
            value = _js_string(n.child_by_field_name("source"))
            if value:
                result.imports.append(value)
            continue
        if n.type != "call_expression":
            continue
        fn = n.child_by_field_name("function")
        args = n.child_by_field_name("arguments")
        named = [a for a in (args.named_children if args else []) if a.type != "comment"]

        if fn is not None and fn.type == "identifier" and _txt(fn) == "require" and named:
            value = _js_string(named[0])
            if value:
                result.imports.append(value)
            continue
        if fn is None or fn.type != "member_expression":
            continue
        obj, prop = fn.child_by_field_name("object"), fn.child_by_field_name("property")
        if obj is None or prop is None:
            continue
        verb, line = _txt(prop), n.start_point.row + 1

        if verb in _JS_VERBS and named:
            path = _js_string(named[0])
            if path is not None and (path.startswith("/") or path == "*"):
                routes.append((_txt(obj), verb, path, named[1:], line))
        elif verb == "use" and named:
            prefix = _js_string(named[0])
            rest = named[1:] if prefix is not None else named
            uses.append((_txt(obj), prefix, _js_names(rest), line))

    for obj, verb, path, rest, line in routes:
        signals = [
            s
            for u_obj, prefix, names, u_line in uses
            if u_obj == obj and u_line < line and (prefix is None or path.startswith(prefix))
            for s in names
        ]
        handler_name = None
        inline_calls: tuple[str, ...] = ()
        if rest:
            *middleware, handler = rest
            signals.extend(_js_names(middleware))
            if handler.type in _JS_NAMEABLE:
                handler_name = _txt(handler).rsplit(".", 1)[-1]
            elif handler.type in ("arrow_function", "function_expression", "function"):
                inline_calls = tuple(_dedupe(c.callee_full for c in _js_calls(handler)))
            else:
                signals.extend(_js_names([handler]))
        result.endpoints.append(
            RawEndpoint(
                method=verb.upper(),
                path=path,
                framework="express",
                line=line,
                handler_name=handler_name,
                handler_line=None,
                signals=tuple(_dedupe(signals)),
                inline_calls=inline_calls,
            )
        )

    result.imports = _dedupe(result.imports)
    return result


# ------------------------------------------------------------------- NestJS

_NEST_VERBS = {
    "Get": "GET", "Post": "POST", "Put": "PUT", "Delete": "DELETE",
    "Patch": "PATCH", "Head": "HEAD", "Options": "OPTIONS", "All": "ALL",
}


def _decorator(node: Node) -> tuple[str, Node | None] | None:
    """(`UseGuards`, arguments node) for `@UseGuards(...)`; (`Public`, None) for `@Public`."""
    expr = next((c for c in node.named_children if c.type != "comment"), None)
    if expr is None:
        return None
    if expr.type == "call_expression":
        fn = expr.child_by_field_name("function")
        if fn is not None and fn.type in _JS_NAMEABLE:
            return _txt(fn).rsplit(".", 1)[-1], expr.child_by_field_name("arguments")
        return None
    if expr.type in _JS_NAMEABLE:
        return _txt(expr).rsplit(".", 1)[-1], None
    return None


def _nest_args(args: Node | None) -> list[Node]:
    return [a for a in (args.named_children if args else []) if a.type != "comment"]


def _nest_join(prefix: str, path: str) -> str:
    parts = [p.strip("/") for p in (prefix, path) if p and p.strip("/")]
    return "/" + "/".join(parts)


def _analyze_nest(root: Node, result: Analysis) -> None:
    for cls in _walk(root):
        if cls.type not in ("class_declaration", "abstract_class_declaration"):
            continue
        decorators = [c for c in cls.children if c.type == "decorator"]
        if cls.parent is not None and cls.parent.type == "export_statement":
            decorators += [c for c in cls.parent.children if c.type == "decorator"]
        prefix, class_signals, is_controller = "", [], False
        for d in decorators:
            parsed = _decorator(d)
            if parsed is None:
                continue
            name, args = parsed
            if name == "Controller":
                is_controller = True
                first = next(iter(_nest_args(args)), None)
                prefix = _js_string(first) or ""
            else:
                class_signals.append(name)
                class_signals.extend(_js_names(_nest_args(args)))
        if not is_controller:
            continue

        body = cls.child_by_field_name("body")
        pending: list[Node] = []
        for child in body.children if body is not None else []:
            if child.type == "decorator":
                pending.append(child)
                continue
            if child.type != "method_definition":
                pending = []
                continue
            name_node = child.child_by_field_name("name")
            verbs, signals, line = [], list(class_signals), None
            for d in pending:
                parsed = _decorator(d)
                if parsed is None:
                    continue
                dec_name, args = parsed
                line = line or d.start_point.row + 1
                if dec_name in _NEST_VERBS:
                    first = next(iter(_nest_args(args)), None)
                    verbs.append((_NEST_VERBS[dec_name], _js_string(first) or ""))
                else:
                    signals.append(dec_name)
                    signals.extend(_js_names(_nest_args(args)))
            pending = []
            if name_node is None:
                continue
            for method, path in verbs:
                result.endpoints.append(
                    RawEndpoint(
                        method=method,
                        path=_nest_join(prefix, path),
                        framework="nestjs",
                        line=line or child.start_point.row + 1,
                        handler_name=_txt(name_node),
                        handler_line=child.start_point.row + 1,
                        signals=tuple(_dedupe(signals)),
                        inline_calls=(),
                    )
                )


def analyze_source(source: bytes, language: str) -> Analysis:
    root = parse_tree(source, language)
    if language == "python":
        return _analyze_python(root)
    if language in JS_FAMILY:
        result = _analyze_javascript(root)
        if language == "typescript":
            _analyze_nest(root, result)
        return result
    return Analysis()
