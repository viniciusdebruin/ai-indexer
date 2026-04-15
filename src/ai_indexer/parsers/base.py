"""Abstract base class for language parsers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ai_indexer.utils.io import ImportResolver


@dataclass
class ParseResult:
    """Unified output from any language parser."""

    external: list[str] = field(default_factory=list)
    """Third-party package names."""

    internal: list[str] = field(default_factory=list)
    """Resolved relative paths of internal imports."""

    functions: list[str] = field(default_factory=list)
    classes: list[str] = field(default_factory=list)
    exports: list[str] = field(default_factory=list)

    has_main_guard: bool = False
    has_listen: bool = False

    docstrings: dict[str, str] = field(default_factory=dict)
    """symbol → first-line docstring/JSDoc."""

    type_hints: dict[str, dict[str, str]] = field(default_factory=dict)
    """function → {param: type}."""

    module_doc: str | None = None
    """Module-level docstring or top JSDoc description."""

    lines: int = 0
    chunks: list[str] = field(default_factory=list)


class BaseParser(ABC):
    """All language parsers implement this interface."""

    #: File extensions this parser handles (lower-case, with leading dot)
    extensions: frozenset[str] = frozenset()

    @abstractmethod
    def parse(self, path: Path, src: str, resolver: "ImportResolver") -> ParseResult:
        """Parse *src* (content of *path*) and return structured metadata."""
        ...

    def can_handle(self, path: Path) -> bool:
        return path.suffix.lower() in self.extensions

    # ── Default chunk splitter (overridden by concrete parsers) ─────────────

    def chunk(self, src: str, path: Path, max_tokens: int = 800) -> list[str]:  # noqa: ARG002
        """Split *src* into semantic chunks. Default: line-based."""
        from ai_indexer.utils.io import count_tokens
        lines = src.splitlines()
        chunks: list[str] = []
        current: list[str] = []
        current_tokens = 0
        for line in lines:
            lt = count_tokens(line)
            if current_tokens + lt > max_tokens and current:
                chunks.append("\n".join(current))
                current = [line]
                current_tokens = lt
            else:
                current.append(line)
                current_tokens += lt
        if current:
            chunks.append("\n".join(current))
        return chunks


class ParserRegistry:
    """Holds and dispatches to registered language parsers."""

    def __init__(self) -> None:
        self._parsers: list[BaseParser] = []

    def register(self, parser: BaseParser) -> None:
        self._parsers.append(parser)

    def get(self, path: Path) -> BaseParser | None:
        for p in self._parsers:
            if p.can_handle(path):
                return p
        return None

    def parse(self, path: Path, src: str, resolver: Any) -> ParseResult:
        parser = self.get(path)
        if parser is not None:
            result = parser.parse(path, src, resolver)
            result.lines = len(src.splitlines())
            result.chunks = parser.chunk(src, path)
            return result
        return ParseResult(lines=len(src.splitlines()))
