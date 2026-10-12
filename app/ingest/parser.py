"""Split source files into function / class / module chunks using tree-sitter."""

from dataclasses import dataclass

import tree_sitter_javascript as tsjs
import tree_sitter_python as tspython
from tree_sitter import Language, Node, Parser

EXTENSIONS = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
}

_PARSERS = {
    "python": Parser(Language(tspython.language())),
    "javascript": Parser(Language(tsjs.language())),
}

_CLASS_NODES = {"class_definition", "class_declaration"}
_FUNC_NODES = {
    "function_definition",
    "function_declaration",
    "generator_function_declaration",
    "method_definition",
}
_FUNC_VALUES = {"arrow_function", "function_expression", "function"}


@dataclass(frozen=True)
class Chunk:
    kind: str  # module | class | function | method
    name: str
    qualified_name: str
    start_line: int  # 1-indexed, inclusive
    end_line: int
    content: str


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


def _visit(
    node: Node,
    scope: list[tuple[str, str]],
    source: bytes,
    chunks: list[Chunk],
    covered: list[tuple[int, int]],
) -> None:
    for child in node.children:
        kind = _definition_kind(child)
        if kind is None:
            _visit(child, scope, source, chunks, covered)
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

        chunks.append(Chunk(kind, name, qualified, start_line, end_line, content))
        if not scope:
            covered.append((outer.start_point.row, outer.end_point.row))

        _visit(child, scope + [(name, kind)], source, chunks, covered)


def _module_chunk(source: bytes, covered: list[tuple[int, int]]) -> Chunk | None:
    lines = source.decode("utf-8", errors="replace").splitlines()
    keep = [
        i
        for i, line in enumerate(lines)
        if line.strip() and not any(a <= i <= b for a, b in covered)
    ]
    if not keep:
        return None
    content = "\n".join(lines[i] for i in keep)
    return Chunk("module", "<module>", "<module>", keep[0] + 1, keep[-1] + 1, content)


def parse_tree(source: bytes, language: str) -> Node:
    return _PARSERS[language].parse(source).root_node


def parse_source(source: bytes, language: str) -> list[Chunk]:
    tree = _PARSERS[language].parse(source)
    chunks: list[Chunk] = []
    covered: list[tuple[int, int]] = []
    _visit(tree.root_node, [], source, chunks, covered)
    module = _module_chunk(source, covered)
    if module is not None:
        chunks.insert(0, module)
    return chunks
