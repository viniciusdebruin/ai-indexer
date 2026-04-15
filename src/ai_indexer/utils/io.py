"""I/O utilities: safe file reading (mmap for large files), token counting,
import path resolution, and gitignore filtering."""

from __future__ import annotations

import fnmatch
import json
import mmap
import os
import re
from pathlib import Path
from typing import Any

# ── Token counting ────────────────────────────────────────────────────────────
try:
    import tiktoken as _tiktoken
    _TOKEN_COUNTER = _tiktoken.get_encoding("cl100k_base")
except ImportError:
    _TOKEN_COUNTER = None

_MMAP_THRESHOLD = 1_048_576  # 1 MB


def count_tokens(text: str) -> int:
    if _TOKEN_COUNTER:
        return len(_TOKEN_COUNTER.encode(text))
    return len(text) // 4


# ── File reading ──────────────────────────────────────────────────────────────

def safe_read_text(path: Path) -> str:
    """Read a text file; use mmap for files > 1 MB to avoid heap pressure."""
    try:
        size = path.stat().st_size
        if size > _MMAP_THRESHOLD:
            with open(path, "rb") as f:
                with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                    return mm.read().decode("utf-8", errors="ignore")
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


# ── Import resolver ───────────────────────────────────────────────────────────

class ImportResolver:
    """Resolves import specifiers to relative file paths within the project."""

    def __init__(
        self,
        root: Path,
        file_index: dict[str, str],
        aliases: dict[str, Path],
        bare_module_names: set[str],
    ) -> None:
        self.root = root
        self.file_index = file_index
        self.aliases = aliases
        self.bare_module_names = bare_module_names

    def resolve_import(
        self, specifier: str, source_file: Path, language: str | None = None
    ) -> str | None:
        specifier = specifier.strip().strip('"').strip("'")
        if not specifier or specifier.startswith("node:"):
            return None

        # Alias resolution (longest-prefix wins)
        for alias, target_dir in sorted(
            self.aliases.items(), key=lambda kv: len(kv[0]), reverse=True
        ):
            if specifier == alias or specifier.startswith(alias + "/"):
                remainder = specifier[len(alias):].lstrip("/")
                resolved = self._resolve_path_or_module(target_dir / remainder)
                if resolved:
                    return resolved

        if specifier.startswith("."):
            return self._resolve_relative(specifier, source_file, language)
        return self._resolve_bare(specifier, source_file, language)

    # ── Internals ────────────────────────────────────────────────────────────

    def _resolve_relative(
        self, specifier: str, source_file: Path, language: str | None
    ) -> str | None:
        if source_file.suffix.lower() == ".py" or language == "py":
            return self._resolve_python_relative(specifier, source_file)
        return self._resolve_path_or_module((source_file.parent / specifier).resolve())

    def _resolve_python_relative(self, specifier: str, source_file: Path) -> str | None:
        try:
            level = len(specifier) - len(specifier.lstrip("."))
            remainder = specifier.lstrip(".")
            parent = source_file.parent
            for _ in range(max(0, level - 1)):
                parent = parent.parent
            base = parent.joinpath(*remainder.split(".")) if remainder else parent
            return self._resolve_path_or_module(base)
        except Exception:
            return None

    def _resolve_bare(
        self, specifier: str, source_file: Path, language: str | None
    ) -> str | None:
        head = specifier.split("/")[0].split(".")[0]
        if head not in self.bare_module_names and head not in self.file_index:
            candidate = self.root / head
            rel = self._resolve_path_or_module(candidate)
            if rel:
                return rel
        if source_file.suffix.lower() == ".py" or language == "py":
            candidate = self.root.joinpath(*specifier.split("."))
            rel = self._resolve_path_or_module(candidate)
            if rel:
                return rel
        return self._resolve_path_or_module(self.root / specifier)

    def _resolve_path_or_module(self, path: Path) -> str | None:
        if path.is_file():
            return self._match_file(path)
        if path.is_dir():
            for name in [
                "index.py", "index.ts", "index.tsx", "index.js",
                "index.jsx", "index.mjs", "index.cjs", "__init__.py",
            ]:
                rel = self._match_file(path / name)
                if rel:
                    return rel
            if path.name in self.file_index:
                return self.file_index[path.name]
        for ext in [".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".json"]:
            rel = self._match_file(path.with_suffix(ext))
            if rel:
                return rel
        stem = path.name
        if stem in self.file_index:
            return self.file_index[stem]
        return None

    def _match_file(self, abs_path: Path) -> str | None:
        try:
            rel = abs_path.resolve().relative_to(self.root).as_posix()
        except Exception:
            return None
        if rel in self.file_index:
            return self.file_index[rel]
        stem = Path(rel).stem
        if stem in self.file_index:
            return self.file_index[stem]
        return None


# ── Import resolution state builder ──────────────────────────────────────────

def build_import_resolution_state(
    root: Path, file_index: dict[str, str]
) -> tuple[dict[str, Path], set[str]]:
    """Read tsconfig.json, package.json, and bunfig.toml to extract aliases."""
    aliases: dict[str, Path] = {}

    # tsconfig.json paths
    tsconfig_path = root / "tsconfig.json"
    if tsconfig_path.exists():
        try:
            tsconfig = json.loads(
                tsconfig_path.read_text(encoding="utf-8", errors="ignore")
            ).get("compilerOptions", {})
            base_url = tsconfig.get("baseUrl", ".")
            for alias, targets in (tsconfig.get("paths", {}) or {}).items():
                if targets:
                    aliases[alias.rstrip("/*")] = (
                        root / base_url / targets[0].rstrip("/*")
                    ).resolve()
        except Exception:
            pass

    # package.json _moduleAliases
    pkg_path = root / "package.json"
    package_json: dict[str, Any] = {}
    if pkg_path.exists():
        try:
            package_json = json.loads(
                pkg_path.read_text(encoding="utf-8", errors="ignore")
            )
            for alias, target in (package_json.get("_moduleAliases", {}) or {}).items():
                try:
                    aliases[alias.rstrip("/*")] = (root / target).resolve()
                except Exception:
                    pass
        except Exception:
            pass

    # bunfig.toml [bundle.alias]
    bunfig_path = root / "bunfig.toml"
    if bunfig_path.exists():
        _tomllib = None
        try:
            import tomllib as _tomllib  # type: ignore[no-redef]
        except ImportError:
            try:
                import tomli as _tomllib  # type: ignore[no-redef]
            except ImportError:
                pass
        if _tomllib is not None:
            try:
                with open(bunfig_path, "rb") as f:
                    bunfig = _tomllib.load(f)
                for _alias, _target in (bunfig.get("bundle", {}).get("alias", {}) or {}).items():
                    try:
                        aliases[_alias.rstrip("/*")] = (root / _target).resolve()
                    except Exception:
                        pass
            except Exception:
                pass

    bare_names: set[str] = set()
    for rel in file_index.values():
        p = Path(rel)
        bare_names.add(p.stem)
        if p.name == "index" and p.parent.name:
            bare_names.add(p.parent.name)
        if len(p.parts) >= 2:
            bare_names.add(p.parts[-2])

    for key in ["name", "main", "module"]:
        val = package_json.get(key)
        if isinstance(val, str):
            bare_names.add(val.split("/")[-1])

    return aliases, {n for n in bare_names if n}


# ── Gitignore filter ──────────────────────────────────────────────────────────

try:
    import pathspec as _pathspec
    _PATHSPEC_AVAILABLE = True
except ImportError:
    _pathspec = None  # type: ignore[assignment]
    _PATHSPEC_AVAILABLE = False


class GitignoreFilter:
    def __init__(self, root: Path) -> None:
        self._patterns: list[tuple[str, bool]] = []
        self._spec: Any = None
        gi = root / ".gitignore"
        raw_lines: list[str] = []
        if gi.exists():
            try:
                for raw in gi.read_text(encoding="utf-8", errors="ignore").splitlines():
                    line = raw.strip()
                    if not line or line.startswith("#"):
                        continue
                    raw_lines.append(line)
                    negated = line.startswith("!")
                    pattern = line[1:] if negated else line
                    self._patterns.append((pattern, negated))
            except OSError:
                pass
        if _PATHSPEC_AVAILABLE and raw_lines:
            try:
                self._spec = _pathspec.PathSpec.from_lines("gitwildmatch", raw_lines)
            except Exception:
                pass

    def should_ignore(self, rel: Path) -> bool:
        if self._spec is not None:
            return bool(self._spec.match_file(rel.as_posix()))
        rel_str = rel.as_posix()
        matched = False
        for pattern, negated in self._patterns:
            if (
                fnmatch.fnmatch(rel.name, pattern)
                or fnmatch.fnmatch(rel_str, pattern)
                or fnmatch.fnmatch(rel_str, f"**/{pattern}")
                or (pattern.endswith("/") and fnmatch.fnmatch(rel.name, pattern.rstrip("/")))
            ):
                matched = not negated
        return matched
