"""TOON format exporter.

TOON is a compact YAML-like text format that reduces repeated JSON keys.
For the `files` section it uses a columnar layout: column headers appear
once, followed by value-only rows — cutting ~40-60 % of tokens vs JSON
for projects with many files.

Format sketch
-------------
files:
  @columns: f ft.value ft.confidence d.value criticality layer ps re br
  @rows:
    src/server.ts entrypoint 0.9 core critical presentation 88 12.4 5
    src/db/connection.ts database 0.95 database critical infrastructure 72 8.1 3
    ...
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ai_indexer.exporters.base import BaseExporter

_SIMPLE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
_RESERVED = frozenset({"true", "false", "null"})

# Columns extracted for the columnar `files` section
_FILE_COLUMNS = (
    "f", "ft_v", "ft_c", "d_v", "d_c", "sd", "l",
    "c", "ep", "cl", "cs", "ps", "fi", "fo", "pr", "re", "br",
)


class ToonExporter(BaseExporter):
    extension = ".toon"

    def export(self, data: dict[str, Any], output_path: Path) -> None:
        output_path.write_text(self._render(data), encoding="utf-8")

    # ── Render ────────────────────────────────────────────────────────────────

    def _render(self, data: dict[str, Any]) -> str:
        parts: list[str] = []

        # Header fields
        for key in ("version", "project", "generated_at"):
            parts.append(f"{key}: {self._scalar(data.get(key, ''))}")

        # Stats block (small, keep key-value)
        parts.append("stats:")
        for k, v in (data.get("stats") or {}).items():
            parts.append(f"  {k}: {self._scalar(v)}")

        # Columnar files section
        parts.append(self._render_files_columnar(data.get("files") or {}))

        # Remaining sections via generic serialiser
        for key in ("hotspots", "execution_flows", "modules"):
            val = data.get(key)
            if val:
                parts.append(f"{key}:")
                parts.append(self._serialize(val, indent=1))

        return "\n".join(parts) + "\n"

    def _render_files_columnar(self, files: dict[str, Any]) -> str:
        if not files:
            return "files: {}"
        lines = ["files:"]
        lines.append("  @columns: " + " ".join(_FILE_COLUMNS))
        lines.append("  @rows:")
        for _path, fd in files.items():
            row = self._extract_row(fd)
            lines.append("    " + " ".join(self._scalar(v) for v in row))
        # Hints / warnings / capabilities appended as key-value after rows
        lines.append("  @detail:")
        for path, fd in files.items():
            hints = fd.get("hints") or {}
            desc  = hints.get("description", "")
            warns = fd.get("warns") or []
            caps  = fd.get("caps") or {}
            if desc or warns or caps:
                lines.append(f"  {self._maybe_quote(path)}:")
                if desc:
                    lines.append(f"    hint: {self._scalar(desc)}")
                for w in warns[:3]:
                    lines.append(f"    warn: {self._scalar(w)}")
                for cap_key, cap_vals in caps.items():
                    if cap_vals:
                        lines.append(
                            f"    {cap_key}: {' '.join(self._scalar(v) for v in cap_vals[:5])}"
                        )
        return "\n".join(lines)

    @staticmethod
    def _extract_row(fd: dict[str, Any]) -> list[Any]:
        ft  = fd.get("ft") or {}
        d   = fd.get("d") or {}
        return [
            fd.get("f", ""),
            ft.get("value", ""),
            ft.get("confidence", 0.0),
            d.get("value", ""),
            d.get("confidence", 0.0),
            fd.get("sd") or "",
            fd.get("l", "u"),
            fd.get("c", "s"),
            fd.get("ep", False),
            fd.get("cl", "l"),
            fd.get("cs", 0),
            fd.get("ps", 0),
            fd.get("fi", 0),
            fd.get("fo", 0),
            fd.get("pr", 0.0),
            fd.get("re", 0.0),
            fd.get("br", 0),
        ]

    # ── Generic serialiser (non-file sections) ───────────────────────────────

    def _serialize(self, obj: Any, indent: int = 0) -> str:
        pad = "  " * indent
        if obj is None:
            return f"{pad}null"
        if isinstance(obj, bool):
            return f"{pad}{'true' if obj else 'false'}"
        if isinstance(obj, int):
            return f"{pad}{obj}"
        if isinstance(obj, float):
            return f"{pad}{obj:.6g}"
        if isinstance(obj, str):
            return f"{pad}{self._scalar(obj)}"
        if isinstance(obj, dict):
            if not obj:
                return f"{pad}{{}}"
            rows = []
            for k, v in obj.items():
                key = self._maybe_quote(str(k))
                rendered = self._serialize(v, indent + 1)
                if isinstance(v, (dict, list)) and v:
                    rows.append(f"{pad}{key}:\n{rendered}")
                else:
                    rows.append(f"{pad}{key}: {rendered.lstrip()}")
            return "\n".join(rows)
        if isinstance(obj, list):
            if not obj:
                return f"{pad}[]"
            rows = []
            for item in obj:
                rendered = self._serialize(item, indent + 1)
                if isinstance(item, (dict, list)) and item:
                    rows.append(f"{pad}-\n{rendered}")
                else:
                    rows.append(f"{pad}- {rendered.lstrip()}")
            return "\n".join(rows)
        return f"{pad}{self._scalar(str(obj))}"

    # ── Scalar helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _scalar(val: Any) -> str:
        if val is None:
            return "null"
        if isinstance(val, bool):
            return "true" if val else "false"
        if isinstance(val, int):
            return str(val)
        if isinstance(val, float):
            return f"{val:.6g}"
        s = str(val)
        if _SIMPLE.match(s) and s not in _RESERVED:
            return s
        escaped = s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        return f'"{escaped}"'

    @staticmethod
    def _maybe_quote(key: str) -> str:
        if _SIMPLE.match(key) and key not in _RESERVED:
            return key
        escaped = key.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
