"""Incremental analysis cache.

Persists per-file metadata keyed by (path + mtime + size).
Flushes to disk every FLUSH_EVERY files to survive crashes mid-run.
"""

from __future__ import annotations

import os
import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger("ai-indexer.cache")

CACHE_FILE = ".aicontext_cache_v8.json"
FLUSH_EVERY = 50  # files


class AnalysisCache:
    def __init__(self, root: Path) -> None:
        self._path = root / CACHE_FILE
        self._data: dict[str, Any] = {}
        self._dirty: int = 0
        self._load()

    # ── Persistence ─────────────────────────────────────────────────────────

    def _load(self) -> None:
        if self._path.exists():
            try:
                self._data = json.loads(
                    self._path.read_text(encoding="utf-8", errors="ignore")
                )
                log.debug("Loaded %d cached entries from %s", len(self._data), self._path)
            except Exception as exc:
                log.warning("Cache load failed (%s) – starting fresh", exc)
                self._data = {}

    def save(self) -> None:
        temp_path = self._path.with_suffix(".tmp")
        try:
            temp_path.write_text(
                json.dumps(self._data, indent=2, ensure_ascii=False), 
                encoding="utf-8"
            )
            os.replace(temp_path, self._path)
            self._dirty = 0
        except Exception as exc:
            log.warning("Cache save failed: %s", exc)
            if temp_path.exists():
                temp_path.unlink()

    # ── Key ─────────────────────────────────────────────────────────────────

    @staticmethod
    def _key(path: Path) -> str:
        try:
            st = path.stat()
            return f"{path.resolve()}:{st.st_mtime:.3f}:{st.st_size}"
        except OSError:
            return str(path.resolve())

    # ── Read/Write ──────────────────────────────────────────────────────────

    def get(self, path: Path) -> dict[str, Any] | None:
        return self._data.get(self._key(path))

    def set(self, path: Path, metadata: dict[str, Any]) -> None:
        self._data[self._key(path)] = metadata
        self._dirty += 1
        if self._dirty >= FLUSH_EVERY:
            log.debug("Cache dirty count reached %d – flushing", FLUSH_EVERY)
            self.save()

    def invalidate(self, path: Path) -> None:
        self._data.pop(self._key(path), None)

    def clear(self) -> None:
        self._data = {}
        self._dirty = 0
