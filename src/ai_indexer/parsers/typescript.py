"""TypeScript / JavaScript language parser.

Uses tree-sitter when available; falls back to regex.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ai_indexer.parsers.base import BaseParser, ParseResult

if TYPE_CHECKING:
    from ai_indexer.utils.io import ImportResolver

# ── tree-sitter setup ────────────────────────────────────────────────────────
_TS_AVAILABLE = False
_TS_PARSER = _TSX_PARSER = _JS_PARSER = None
_TS_IMPORT_QUERY = _JS_IMPORT_QUERY = None

try:
    from tree_sitter import Language, Parser, Query  # noqa: F401
    import tree_sitter_typescript
    import tree_sitter_javascript

    _TS_LANG  = Language(tree_sitter_typescript.language_typescript())
    _TSX_LANG = Language(tree_sitter_typescript.language_tsx())
    _JS_LANG  = Language(tree_sitter_javascript.language())

    def _make_parser(lang: Any) -> Any:
        try:
            return Parser(lang)
        except TypeError:
            p = Parser()
            p.set_language(lang)
            return p

    _TS_PARSER  = _make_parser(_TS_LANG)
    _TSX_PARSER = _make_parser(_TSX_LANG)
    _JS_PARSER  = _make_parser(_JS_LANG)

    # ── Query runner: handles tree-sitter < 0.25 and >= 0.25 ────────────────
    # < 0.25 : Query.captures(node)  → list[tuple[Node, str]]
    # >= 0.25: QueryCursor(Query).captures(node) → dict[str, list[Node]]
    try:
        from tree_sitter import QueryCursor as _QueryCursor  # >= 0.25

        def _make_query(lang: Any, src: str) -> Any:
            return Query(lang, src)

        def _run_captures(query: Any, node: Any) -> list[tuple[Any, str]]:
            pairs: list[tuple[Any, str]] = []
            for cap_name, nodes in _QueryCursor(query).captures(node).items():
                for n in nodes:
                    pairs.append((n, cap_name))
            return pairs

    except ImportError:
        # tree-sitter < 0.25

        def _make_query(lang: Any, src: str) -> Any:
            return lang.query(src)

        def _run_captures(query: Any, node: Any) -> list[tuple[Any, str]]:
            return list(query.captures(node))

    _IMPORT_QUERY_SRC = """
    (import_statement source: (string (string_fragment) @module))
    (export_statement source: (string (string_fragment) @module))
    """
    try:
        _TS_IMPORT_QUERY = _make_query(_TS_LANG, _IMPORT_QUERY_SRC)
        _JS_IMPORT_QUERY = _make_query(_JS_LANG, _IMPORT_QUERY_SRC)
    except Exception:
        pass

    _TS_AVAILABLE = True
except ImportError:
    pass

# ── Regex fallbacks ──────────────────────────────────────────────────────────
_RE_JS_IMPORT        = re.compile(r"import\s+(?:type\s+)?(?:[^'\"]+?from\s+)?['\"]([^'\"]+)['\"]")
_RE_JS_REQUIRE       = re.compile(r"require\(\s*['\"]([^'\"]+)['\"]\s*\)")
_RE_JS_DYN_IMPORT    = re.compile(r"import\s*\(\s*['\"]([^'\"]+)['\"]\s*\)")
_RE_JS_EXPORT_FN     = re.compile(r"(?:export\s+)?(?:async\s+)?function\s+(\*?\s*[A-Za-z_$][\w$]*)\s*\(")
_RE_JS_EXPORT_CLASS  = re.compile(r"(?:export\s+)?class\s+([A-Za-z_$][\w$]*)")
_RE_JS_EXPORT_CONST  = re.compile(r"(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=")
_RE_JS_EXPORT_NAMED  = re.compile(r"export\s+\{([^}]+)\}")
_RE_JS_DEFAULT_EXPORT = re.compile(r"export\s+default\s+([A-Za-z_$][\w$]*)")
_RE_JS_LISTEN        = re.compile(r"\.listen\s*\(")

_TS_JS_SUFFIXES = frozenset({".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"})


class TypeScriptParser(BaseParser):
    extensions = _TS_JS_SUFFIXES

    def parse(self, path: Path, src: str, resolver: "ImportResolver") -> ParseResult:
        result = ParseResult()
        result.has_listen = bool(_RE_JS_LISTEN.search(src))

        if _TS_AVAILABLE:
            self._parse_tree_sitter(path, src, resolver, result)
        else:
            self._parse_regex(path, src, resolver, result)

        # Dynamic imports via regex (supplements tree-sitter)
        for dyn_match in _RE_JS_DYN_IMPORT.finditer(src):
            mod = dyn_match.group(1)
            resolved = resolver.resolve_import(mod, path)
            if resolved:
                if resolved not in result.internal:
                    result.internal.append(resolved)
            elif not mod.startswith("node:"):
                head = mod.split("/")[0]
                if head not in result.external:
                    result.external.append(head)

        # Fallback module_doc from leading JSDoc (regex path only)
        if result.module_doc is None:
            jsdoc_match: re.Match[str] | None = re.match(r"/\*\*(.*?)\*/", src, re.DOTALL)
            if jsdoc_match:
                for line in jsdoc_match.group(0).split("\n"):
                    line = line.strip().lstrip("*").strip()
                    if line and not line.startswith("@") and line not in ("/**", "*/", "/"):
                        result.module_doc = line
                        break

        result.functions = list(dict.fromkeys(result.functions))[:20]
        result.classes   = list(dict.fromkeys(result.classes))[:20]
        result.exports   = list(dict.fromkeys(result.exports))[:20]
        result.external  = sorted(set(result.external))
        result.internal  = sorted(set(result.internal))
        return result

    # ── Tree-sitter path ─────────────────────────────────────────────────────

    def _parse_tree_sitter(
        self, path: Path, src: str, resolver: "ImportResolver", result: ParseResult
    ) -> None:
        suffix = path.suffix.lower()
        parser = _TSX_PARSER if suffix == ".tsx" else (_TS_PARSER if suffix == ".ts" else _JS_PARSER)
        query  = _TS_IMPORT_QUERY if suffix in {".ts", ".tsx"} else _JS_IMPORT_QUERY
        if parser is None:
            self._parse_regex(path, src, resolver, result)
            return

        tree = parser.parse(bytes(src, "utf-8"))

        if query is not None:
            for node, cap_name in _run_captures(query, tree.root_node):
                if cap_name == "module":
                    mod = node.text.decode("utf-8").strip("'\"")
                    resolved = resolver.resolve_import(mod, path)
                    if resolved:
                        result.internal.append(resolved)
                    elif not mod.startswith("node:"):
                        result.external.append(mod.split("/")[0])

        # File-level JSDoc
        for child in tree.root_node.children:
            if child.type == "comment":
                text = child.text.decode("utf-8")
                if text.startswith("/**"):
                    for line in text.split("\n"):
                        line = line.strip().lstrip("*").strip()
                        if line and not line.startswith("@") and line not in ("/**", "*/", "/"):
                            result.module_doc = line
                            break
                break
            elif child.is_named:
                break

        self._walk_tree(tree.root_node, path, resolver, result)

    def _walk_tree(self, node: Any, path: Path, resolver: "ImportResolver", result: ParseResult) -> None:
        if node.type in {"function_declaration", "method_definition"}:
            name_node = node.child_by_field_name("name")
            if name_node:
                name = name_node.text.decode("utf-8")
                result.functions.append(name)
                comment = self._extract_jsdoc(node)
                if comment:
                    result.docstrings[name] = comment
        elif node.type == "class_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                name = name_node.text.decode("utf-8")
                result.classes.append(name)
                comment = self._extract_jsdoc(node)
                if comment:
                    result.docstrings[name] = comment
        elif node.type == "lexical_declaration":
            for child in node.children:
                if child.type == "variable_declarator":
                    name_node = child.child_by_field_name("name")
                    if name_node:
                        result.functions.append(name_node.text.decode("utf-8"))
        for child in node.children:
            self._walk_tree(child, path, resolver, result)

    @staticmethod
    def _extract_jsdoc(node: Any) -> str | None:
        prev = node.prev_sibling
        if prev and prev.type == "comment":
            text: str = str(prev.text.decode("utf-8"))
            if text.startswith("/**"):
                for line in text.split("\n"):
                    line = line.strip().lstrip("*").strip()
                    if line and not line.startswith("@"):
                        return line
        return None

    # ── Regex fallback ───────────────────────────────────────────────────────

    def _parse_regex(
        self, path: Path, src: str, resolver: "ImportResolver", result: ParseResult
    ) -> None:
        for m in _RE_JS_IMPORT.finditer(src):
            self._add_import(m.group(1), path, resolver, result)
        for m in _RE_JS_REQUIRE.finditer(src):
            self._add_import(m.group(1), path, resolver, result)
        result.functions.extend(
            m.group(1).replace("*", "").strip() for m in _RE_JS_EXPORT_FN.finditer(src)
        )
        result.classes.extend(m.group(1) for m in _RE_JS_EXPORT_CLASS.finditer(src))
        result.functions.extend(m.group(1) for m in _RE_JS_EXPORT_CONST.finditer(src))
        for m in _RE_JS_EXPORT_NAMED.finditer(src):
            for item in m.group(1).split(","):
                item = item.strip()
                if item:
                    result.exports.append(item.split(" as ")[0].strip())
        for m in _RE_JS_DEFAULT_EXPORT.finditer(src):
            result.exports.append(m.group(1))

    @staticmethod
    def _add_import(
        mod: str, path: Path, resolver: "ImportResolver", result: ParseResult
    ) -> None:
        resolved = resolver.resolve_import(mod, path)
        if resolved:
            result.internal.append(resolved)
        elif not mod.startswith("node:"):
            result.external.append(mod.split("/")[0])

    def chunk(self, src: str, path: Path, max_tokens: int = 800) -> list[str]:
        if not _TS_AVAILABLE:
            return super().chunk(src, path, max_tokens)
        from ai_indexer.utils.io import count_tokens
        suffix = path.suffix.lower()
        parser = _TSX_PARSER if suffix == ".tsx" else (_TS_PARSER if suffix == ".ts" else _JS_PARSER)
        if parser is None:
            return super().chunk(src, path, max_tokens)
        try:
            tree = parser.parse(bytes(src, "utf-8"))
            chunks: list[str] = []
            current: list[str] = []
            current_tokens = 0
            for child in tree.root_node.children:
                node_str = child.text.decode("utf-8")
                nt = count_tokens(node_str)
                if current_tokens + nt > max_tokens and current:
                    chunks.append("\n".join(current))
                    current = [node_str]
                    current_tokens = nt
                else:
                    current.append(node_str)
                    current_tokens += nt
            if current:
                chunks.append("\n".join(current))
            return chunks
        except Exception:
            return super().chunk(src, path, max_tokens)
