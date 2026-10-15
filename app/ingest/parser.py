"""Split source files into function / class / module chunks using tree-sitter,
and extract cheap, deterministic facts about each (signature, docstring,
cyclomatic-style complexity, size)."""

import ast
import re
from dataclasses import dataclass

import tree_sitter_javascript as tsjs
import tree_sitter_python as tspython
import tree_sitter_typescript as tsts
from tree_sitter import Language, Node, Parser

EXTENSIONS = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".mts": "typescript",
    ".cts": "typescript",
}

# Languages that share the JavaScript grammar family (same node types for our purposes).
JS_FAMILY = frozenset({"javascript", "typescript"})

_PARSERS = {
    "python": Parser(Language(tspython.language())),
    "javascript": Parser(Language(tsjs.language())),
    "typescript": Parser(Language(tsts.language_typescript())),
}
# `.tsx` needs the JSX-aware grammar; used when plain TypeScript parsing hits errors.
_TSX_PARSER = Parser(Language(tsts.language_tsx()))

_CLASS_NODES = {"class_definition", "class_declaration", "abstract_class_declaration"}
_FUNC_NODES = {
    "function_definition",
    "function_declaration",
    "generator_function_declaration",
    "method_definition",
}
_FUNC_VALUES = {"arrow_function", "function_expression", "function"}

# Node types that add a branch. Complexity = 1 + number of these (a cheap
# McCabe approximation; good enough to rank "where is the hairy code").
_DECISIONS = {
    "python": {
        "if_statement",
        "elif_clause",
        "for_statement",
        "while_statement",
        "except_clause",
        "conditional_expression",
        "boolean_operator",
        "for_in_clause",
        "case_clause",
    },
    "javascript": {
        "if_statement",
        "for_statement",
        "for_in_statement",
        "while_statement",
        "do_statement",
        "switch_case",
        "catch_clause",
        "ternary_expression",
    },
}
_DECISIONS["typescript"] = _DECISIONS["javascript"]
_JS_LOGICAL = {"&&", "||", "??"}

MAX_SIGNATURE = 200
MAX_DOC = 600


@dataclass(frozen=True)
class Chunk:
    kind: str  # module | class | function | method
    name: str
    qualified_name: str
    start_line: int  # 1-indexed, inclusive
    end_line: int
    content: str
    signature: str = ""
    doc: str = ""
    complexity: int = 0
    loc: int = 0  # lines of the whole definition (class: including methods)


def _text(source: bytes, start: int, end: int) -> str:
    return source[start:end].decode("utf-8", errors="replace")


def _definition_kind(node: Node) -> str | None:
    if node.type in _CLASS_NODES:
        return "class"
    if node.type in _FUNC_NODES:
        return "function"
    if node.type == "variable_declarator":
        value = node.child_by_field_name("value")
        if value is not None and value.type in _FUNC_VALUES:
            return "function"
    return None


def _outer(node: Node) -> Node:
    """Widen a definition to include decorators / its `const x =` declaration."""
    parent = node.parent
    if parent is None:
        return node
    if parent.type == "decorated_definition":
        return parent
    if node.type == "variable_declarator" and parent.type in (
        "lexical_declaration",
        "variable_declaration",
    ):
        declarators = [c for c in parent.children if c.type == "variable_declarator"]
        if len(declarators) == 1:
            return parent
    return node


def _name(node: Node, source: bytes) -> str:
    name = node.child_by_field_name("name")
    return _text(source, name.start_byte, name.end_byte) if name else "<anonymous>"


def _first_nested_definition_start(node: Node) -> int | None:
    for child in node.children:
        if _definition_kind(child) is not None:
            return _outer(child).start_byte
        found = _first_nested_definition_start(child)
        if found is not None:
            return found
    return None


# ------------------------------------------------------------------- facts


def _body_of(node: Node) -> Node | None:
    """The body node of a function/class/arrow-function declarator."""
    body = node.child_by_field_name("body")
    if body is None and node.type == "variable_declarator":
        value = node.child_by_field_name("value")
        body = value.child_by_field_name("body") if value is not None else None
    return body


def _signature(node: Node, outer: Node, source: bytes) -> str:
    """`def login(email: str, password: str) -> dict` without decorators/body."""
    body = _body_of(node)
    start = node.start_byte
    if node.type == "variable_declarator" and outer is not node:
        start = outer.start_byte  # keep the `const` keyword
    if body is None:
        end = min(node.end_byte, start + MAX_SIGNATURE * 2)
    else:
        end = body.start_byte
    text = " ".join(_text(source, start, end).split())
    text = re.sub(r"\s*(=>|\{|:)\s*$", "", text)
    return text[:MAX_SIGNATURE]


def _first_sentence(text: str) -> str:
    text = " ".join(text.split())
    m = re.search(r"(.+?[.!?])(\s|$)", text)
    return (m.group(1) if m else text)[:MAX_DOC]


def _python_docstring(body: Node | None) -> str:
    if body is None:
        return ""
    for stmt in body.named_children:
        if stmt.type == "comment":
            continue
        if stmt.type == "expression_statement":
            inner = stmt.named_children[0] if stmt.named_children else None
            if inner is not None and inner.type == "string":
                try:
                    value = ast.literal_eval(inner.text.decode("utf-8", errors="replace"))
                except (ValueError, SyntaxError):
                    return ""
                return _first_sentence(value) if isinstance(value, str) else ""
        return ""
    return ""


_COMMENT_STRIP = re.compile(r"^\s*(/\*+|\*+/|\*|//+)\s?", re.M)


def _js_leading_comment(outer: Node, source: bytes) -> str:
    """JSDoc / `//` comment block directly above a definition."""
    anchor = outer.parent if outer.parent is not None and outer.parent.type == "export_statement" else outer
    prev = anchor.prev_sibling
    lines: list[str] = []
    expected_row = anchor.start_point.row - 1
    while prev is not None and prev.type == "comment" and prev.end_point.row >= expected_row:
        lines.insert(0, _text(source, prev.start_byte, prev.end_byte))
        expected_row = prev.start_point.row - 1
        prev = prev.prev_sibling
    if not lines:
        return ""
    cleaned = _COMMENT_STRIP.sub("", "\n".join(lines)).replace("*/", "")
    cleaned = "\n".join(
        ln for ln in cleaned.splitlines() if not ln.strip().startswith("@")
    )  # drop @param / @returns tags
    return _first_sentence(cleaned)


def _complexity(node: Node, language: str) -> int:
    decisions = _DECISIONS[language]
    count = 1
    stack = [node]
    while stack:
        n = stack.pop()
        if n.type in decisions:
            count += 1
        elif language in JS_FAMILY and n.type == "binary_expression":
            op = n.child_by_field_name("operator")
            if op is not None and op.type in _JS_LOGICAL:
                count += 1
        stack.extend(n.children)
    return count


def _doc(node: Node, outer: Node, source: bytes, language: str) -> str:
    if language == "python":
        return _python_docstring(node.child_by_field_name("body"))
    return _js_leading_comment(outer, source)


def _module_doc(root: Node, source: bytes, language: str) -> str:
    if language == "python":
        return _python_docstring(root)
    first = next((c for c in root.children if c.type != "hashbang_line"), None)
    if first is not None and first.type == "comment":
        cleaned = _COMMENT_STRIP.sub("", _text(source, first.start_byte, first.end_byte))
        return _first_sentence(cleaned.replace("*/", ""))
    return ""


# ------------------------------------------------------------------ walking


def _visit(
    node: Node,
    scope: list[tuple[str, str]],
    source: bytes,
    language: str,
    chunks: list[Chunk],
    covered: list[tuple[int, int]],
) -> None:
    for child in node.children:
        kind = _definition_kind(child)
        if kind is None:
            _visit(child, scope, source, language, chunks, covered)
            continue

        outer = _outer(child)
        name = _name(child, source)
        if kind == "function" and scope and scope[-1][1] == "class":
            kind = "method"
        qualified = ".".join([s[0] for s in scope] + [name])

        end_byte = outer.end_byte
        if kind == "class":
            # Class chunk holds the header and fields only; methods get their own chunks.
            nested = _first_nested_definition_start(child)
            if nested is not None:
                end_byte = nested
        content = _text(source, outer.start_byte, end_byte).rstrip()
        start_line = outer.start_point.row + 1
        end_line = start_line + content.count("\n")
        loc = outer.end_point.row - outer.start_point.row + 1

        chunks.append(
            Chunk(
                kind,
                name,
                qualified,
                start_line,
                end_line,
                content,
                signature=_signature(child, outer, source),
                doc=_doc(child, outer, source, language),
                complexity=_complexity(child, language),
                loc=loc,
            )
        )
        if not scope:
            covered.append((outer.start_point.row, outer.end_point.row))

        _visit(child, scope + [(name, kind)], source, language, chunks, covered)


def _module_chunk(
    source: bytes, covered: list[tuple[int, int]], doc: str, language: str, root: Node
) -> Chunk | None:
    lines = source.decode("utf-8", errors="replace").splitlines()
    keep = [
        i
        for i, line in enumerate(lines)
        if line.strip() and not any(a <= i <= b for a, b in covered)
    ]
    if not keep:
        return None
    content = "\n".join(lines[i] for i in keep)
    return Chunk(
        "module",
        "<module>",
        "<module>",
        keep[0] + 1,
        keep[-1] + 1,
        content,
        doc=doc,
        complexity=_complexity(root, language),
        loc=len(keep),
    )


def parse_tree(source: bytes, language: str) -> Node:
    root = _PARSERS[language].parse(source).root_node
    if language == "typescript" and root.has_error:
        alt = _TSX_PARSER.parse(source).root_node
        if not alt.has_error:
            return alt
    return root


def parse_source(source: bytes, language: str) -> list[Chunk]:
    root = parse_tree(source, language)
    chunks: list[Chunk] = []
    covered: list[tuple[int, int]] = []
    _visit(root, [], source, language, chunks, covered)
    module = _module_chunk(source, covered, _module_doc(root, source, language), language, root)
    if module is not None:
        chunks.insert(0, module)
    return chunks


def count_loc(source: bytes) -> int:
    """Non-blank lines in a file."""
    return sum(1 for line in source.splitlines() if line.strip())
