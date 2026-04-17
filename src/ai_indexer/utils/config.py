"""YAML configuration loader for .indexer.yaml project overrides."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

log = logging.getLogger("ai-indexer.config")

_YAML_AVAILABLE = False
try:
    import yaml as _yaml  # type: ignore[import-untyped]
    _YAML_AVAILABLE = True
except ImportError:
    pass

CONFIG_FILENAME = ".indexer.yaml"


class IndexerConfig:
    """Resolved configuration merging .indexer.yaml with built-in defaults."""

    def __init__(self, data: dict[str, Any]) -> None:
        self._d = data

    @property
    def exclude_dirs(self) -> set[str]:
        return set[str](self._d.get("exclude_dirs", []))

    @property
    def exclude_patterns(self) -> tuple[str, ...]:
        return tuple[str, ...](self._d.get("exclude_patterns", []))

    @property
    def extra_text_filenames(self) -> frozenset[str]:
        return frozenset[str](self._d.get("text_files", {}).get("extra_names", []))

    @property
    def criticality_overrides(self) -> dict[str, str]:
        return dict[str, str](self._d.get("criticality_overrides", {}))

    @property
    def domain_overrides(self) -> dict[str, str]:
        return dict[str, str](self._d.get("domain_overrides", {}))

    @property
    def max_depth(self) -> int:
        return int(self._d.get("max_depth", 8))

    @property
    def max_workers(self) -> int:
        raw = int(self._d.get("max_workers", 0))
        if raw <= 0:
            import os
            return min(32, (os.cpu_count() or 4) * 2)
        return raw

    @property
    def output_formats(self) -> list[str]:
        return list(self._d.get("output_formats", ["toon", "html", "md"]))

    @property
    def output_dir(self) -> str:
        return str(self._d.get("output_dir", "."))

    @property
    def chunk_max_tokens(self) -> int:
        return int(self._d.get("chunk_max_tokens", 800))

    @property
    def type_segment_rules(self) -> list[tuple[str, str] | tuple[str, str, float]]:
        return list(self._d.get("type_segment_rules", []))

    @property
    def type_name_rules(self) -> list[tuple[str, str] | tuple[str, str, float]]:
        return list(self._d.get("type_name_rules", []))

    @property
    def type_suffix_rules(self) -> dict[str, tuple[str, float]]:
        return dict(self._d.get("type_suffix_rules", {}))

    @property
    def type_exact_name_rules(self) -> dict[str, tuple[str, float]]:
        return dict(self._d.get("type_exact_name_rules", {}))

    @property
    def include_patterns(self) -> list[str]:
        return list(self._d.get("include_patterns", []))

    @property
    def security_enabled(self) -> bool:
        return bool(self._d.get("security", {}).get("enabled", True))

    @property
    def instruction_file(self) -> str:
        return str(self._d.get("instruction_file", ""))

    @property
    def git_include_logs(self) -> bool:
        return bool(self._d.get("git", {}).get("include_logs", False))

    @property
    def git_logs_count(self) -> int:
        return int(self._d.get("git", {}).get("logs_count", 10))

    @property
    def git_include_diffs(self) -> bool:
        return bool(self._d.get("git", {}).get("include_diffs", False))

    @property
    def git_sort_by_changes(self) -> bool:
        return bool(self._d.get("git", {}).get("sort_by_changes", False))

    @property
    def git_sort_max_commits(self) -> int:
        return int(self._d.get("git", {}).get("sort_max_commits", 100))


def load_config(root: Path) -> IndexerConfig:
    """Load .indexer.yaml from *root*; return defaults if not found or YAML unavailable."""
    config_path = root / CONFIG_FILENAME
    if not config_path.exists():
        return IndexerConfig({})
    if not _YAML_AVAILABLE:
        log.warning(
            "%s found but pyyaml is not installed. Install the 'full' extra to enable YAML config support.",
            CONFIG_FILENAME,
        )
        return IndexerConfig({})
    try:
        with open(config_path, encoding="utf-8") as f:
            data = _yaml.safe_load(f) or {}
        if not isinstance(data, dict):
            log.warning("%s must contain a mapping at the top level; using defaults", config_path)
            return IndexerConfig({})
        log.info("Loaded config from %s", config_path)
        return IndexerConfig(data)
    except Exception as exc:
        log.warning("Failed to parse %s (%s) - using defaults", config_path, exc)
        return IndexerConfig({})


def validate_config(root: Path) -> tuple[bool, str]:
    """Validate .indexer.yaml syntax without falling back to defaults."""
    config_path = root / CONFIG_FILENAME
    if not config_path.exists():
        return True, "No config file found."
    if not _YAML_AVAILABLE:
        return False, "pyyaml is not installed."
    try:
        with open(config_path, encoding="utf-8") as f:
            data = _yaml.safe_load(f)
        if data is not None and not isinstance(data, dict):
            return False, f"{CONFIG_FILENAME} must contain a mapping at the top level."
        return True, f"{CONFIG_FILENAME} is valid."
    except Exception as exc:
        return False, str(exc)
