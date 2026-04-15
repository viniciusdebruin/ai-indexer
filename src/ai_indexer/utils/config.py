"""YAML configuration loader for .indexer.yaml project overrides."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

log = logging.getLogger("ai-indexer.config")

_YAML_AVAILABLE = False
try:
    import yaml as _yaml
    _YAML_AVAILABLE = True
except ImportError:
    pass

CONFIG_FILENAME = ".indexer.yaml"


class IndexerConfig:
    """Resolved configuration merging .indexer.yaml with built-in defaults."""

    def __init__(self, data: dict[str, Any]) -> None:
        self._d = data

    # ── Accessors ────────────────────────────────────────────────────────────

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


def load_config(root: Path) -> IndexerConfig:
    """Load .indexer.yaml from *root*; return defaults if not found or YAML unavailable."""
    config_path = root / CONFIG_FILENAME
    if not config_path.exists():
        return IndexerConfig({})

    if not _YAML_AVAILABLE:
        log.warning(
            "%s found but pyyaml is not installed — using defaults. "
            "Run: pip install pyyaml",
            CONFIG_FILENAME,
        )
        return IndexerConfig({})

    try:
        with open(config_path, encoding="utf-8") as f:
            data = _yaml.safe_load(f) or {}
        log.info("Loaded config from %s", config_path)
        return IndexerConfig(data)
    except Exception as exc:
        log.warning("Failed to parse %s (%s) — using defaults", config_path, exc)
        return IndexerConfig({})
