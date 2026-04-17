"""File discovery and import-index helpers."""

from __future__ import annotations

import fnmatch
import logging
from pathlib import Path

from ai_indexer.utils.config import IndexerConfig
from ai_indexer.utils.io import GitignoreFilter

log = logging.getLogger("ai-indexer.discovery")


def resolve_scan_roots(root: Path, ignore_dirs: frozenset[str]) -> list[Path]:
    """Return the directories that should actually be walked."""
    src_at_root = root / "src"
    if src_at_root.is_dir():
        log.info("src/ found at root â€” restricting analysis to %s", src_at_root)
        return [src_at_root]

    nested: list[Path] = []
    try:
        for child in sorted(root.iterdir()):
            if not child.is_dir() or child.name in ignore_dirs:
                continue
            candidate = child / "src"
            if candidate.is_dir():
                nested.append(candidate)
    except PermissionError:
        pass

    if nested:
        log.info(
            "No root src/ â€” scanning %d nested src/ dir(s): %s",
            len(nested),
            [str(s.relative_to(root)) for s in nested],
        )
        return nested

    return [root]


def collect_files(
    root: Path,
    config: IndexerConfig,
    ignore_dirs: frozenset[str],
    ignore_patterns: tuple[str, ...],
    generated_files: frozenset[str],
    text_suffixes: frozenset[str],
    special_text_filenames: frozenset[str],
) -> list[Path]:
    """Collect candidate text files for analysis."""
    gi = GitignoreFilter(root)
    special_names = special_text_filenames | config.extra_text_filenames
    result: list[Path] = []

    scan_roots = resolve_scan_roots(root, ignore_dirs)

    for scan_root in scan_roots:
        for p in scan_root.rglob("*"):
            if not p.is_file():
                continue
            if p.name in generated_files:
                continue
            rel = p.relative_to(root)
            parts = rel.parts
            if any(part in ignore_dirs for part in parts[:-1]):
                continue
            if any(fnmatch.fnmatch(p.name, pat) for pat in ignore_patterns):
                continue
            if gi.should_ignore(rel):
                continue
            suffix = p.suffix.lower()
            if suffix not in text_suffixes and p.name not in special_names:
                continue
            result.append(p)

    include_pats = config.include_patterns
    if include_pats:
        result = [
            p for p in result
            if any(
                fnmatch.fnmatch(p.relative_to(root).as_posix(), pat)
                for pat in include_pats
            )
        ]

    return result


def build_file_index(root: Path, paths: list[Path]) -> dict[str, str]:
    """Build lookup keys for files and partial import resolution."""
    idx: dict[str, str] = {}
    for p in paths:
        rel = p.relative_to(root).as_posix()
        idx[rel] = rel
        idx[p.name] = rel
        idx[p.stem] = rel
        if len(p.parts) >= 2:
            idx[f"{p.parts[-2]}/{p.stem}"] = rel
            idx[p.parent.as_posix()] = rel
            idx["/".join(p.parts[-2:])] = rel
    return idx

