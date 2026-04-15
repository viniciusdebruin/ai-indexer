"""MCP (Model Context Protocol) server — JSON-RPC 2.0 over stdio.

100% backward-compatible with the v7.1 interface.
"""

from __future__ import annotations

import json
import logging
import sys
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ai_indexer.core.models import FileMetadata

log = logging.getLogger("ai-indexer.mcp")


class MCPServer:
    """
    Serve targeted queries against an analysed project index via JSON-RPC 2.0.

    Start with the ``--mcp`` CLI flag.  Each request/response is a single
    newline-delimited JSON line on stdin/stdout.

    Supported methods
    -----------------
    get_dependents(file_path)       → list of files that import *file_path*
    search_symbol(symbol_name)      → files + matching symbol names
    get_file_summary(file_path)     → hints + deps + v8 metrics for one file
    list_hotspots(n=10)             → top-N files by priority score
    list_orphans()                  → files with no fan-in and not entrypoints
    list_by_blast_radius(n=10)      → top-N files by blast_radius (new in v8)
    list_refactor_candidates(n=10)  → top-N files by refactor_effort (new in v8)
    """

    def __init__(
        self,
        files: dict[str, "FileMetadata"],
        graph: dict[str, list[str]],
        reverse_graph: dict[str, list[str]],
    ) -> None:
        self._files = files
        self._graph = graph
        self._rev   = reverse_graph

    # ── Query methods ─────────────────────────────────────────────────────────

    def get_dependents(self, file_path: str) -> list[str]:
        return list(self._rev.get(file_path, []))

    def search_symbol(self, symbol_name: str) -> list[dict[str, Any]]:
        needle = symbol_name.lower()
        hits: list[dict[str, Any]] = []
        for path, fd in self._files.items():
            caps = fd.capabilities
            all_sym: list[str] = (
                caps.get("functions", []) + caps.get("classes", []) + caps.get("exports", [])
            )
            matched = [s for s in all_sym if needle in s.lower()]
            if matched:
                hits.append({"file": path, "symbols": matched[:10]})
        return hits

    def get_file_summary(self, file_path: str) -> dict[str, Any] | None:
        fd = self._files.get(file_path)
        if fd is None:
            return None
        return {
            "file":                fd.file,
            "hints":               fd.hints,
            "module_doc":          fd.module_doc,
            "file_type":           fd.file_type.value,
            "domain":              fd.domain.value,
            "layer":               fd.layer,
            "criticality":         fd.criticality,
            "entrypoint":          fd.entrypoint,
            "complexity_label":    fd.complexity_label,
            "complexity_score":    fd.complexity_score,
            "priority_score":      fd.priority_score,
            "fan_in":              fd.fan_in,
            "fan_out":             fd.fan_out,
            "pagerank":            round(fd.pagerank, 5),
            "refactor_effort":     round(fd.refactor_effort, 4),
            "blast_radius":        fd.blast_radius,
            "dependencies":        fd.dependencies[:10],
            "internal_dependencies": fd.internal_dependencies[:10],
            "warnings":            fd.warnings,
            "capabilities":        {k: v[:8] for k, v in fd.capabilities.items() if v},
        }

    def list_hotspots(self, n: int = 10) -> list[dict[str, Any]]:
        return [
            {
                "file":           fd.file,
                "priority_score": fd.priority_score,
                "pagerank":       round(fd.pagerank, 5),
                "fan_in":         fd.fan_in,
                "domain":         fd.domain.value,
                "criticality":    fd.criticality,
                "refactor_effort": round(fd.refactor_effort, 4),
                "blast_radius":   fd.blast_radius,
            }
            for fd in sorted(self._files.values(), key=lambda f: f.priority_score, reverse=True)[:n]
        ]

    def list_orphans(self) -> list[str]:
        return [
            fd.file for fd in self._files.values()
            if fd.fan_in == 0
            and not fd.entrypoint
            and fd.file_type.value not in {"docs", "config", "asset", "template"}
        ]

    def list_by_blast_radius(self, n: int = 10) -> list[dict[str, Any]]:
        """New in v8: top files by 2nd-degree impact radius."""
        return [
            {"file": fd.file, "blast_radius": fd.blast_radius, "fan_in": fd.fan_in}
            for fd in sorted(self._files.values(), key=lambda f: f.blast_radius, reverse=True)[:n]
        ]

    def list_refactor_candidates(self, n: int = 10) -> list[dict[str, Any]]:
        """New in v8: files where refactoring is highest-effort."""
        return [
            {
                "file":           fd.file,
                "refactor_effort": round(fd.refactor_effort, 4),
                "complexity_score": fd.complexity_score,
                "fan_in":         fd.fan_in,
            }
            for fd in sorted(self._files.values(), key=lambda f: f.refactor_effort, reverse=True)[:n]
        ]

    # ── JSON-RPC 2.0 dispatch ─────────────────────────────────────────────────

    _METHODS: dict[str, str] = {
        "get_dependents":          "get_dependents",
        "search_symbol":           "search_symbol",
        "get_file_summary":        "get_file_summary",
        "list_hotspots":           "list_hotspots",
        "list_orphans":            "list_orphans",
        "list_by_blast_radius":    "list_by_blast_radius",
        "list_refactor_candidates":"list_refactor_candidates",
    }

    def _dispatch(self, req: dict[str, Any]) -> dict[str, Any]:
        req_id = req.get("id")
        method = req.get("method", "")
        params = req.get("params") or {}

        attr = self._METHODS.get(method)
        if attr is None:
            return {
                "jsonrpc": "2.0", "id": req_id,
                "error": {"code": -32601, "message": f"Method not found: {method!r}"},
            }
        try:
            handler = getattr(self, attr)
            if method == "get_dependents":
                result = handler(params.get("file_path", ""))
            elif method == "search_symbol":
                result = handler(params.get("symbol_name", ""))
            elif method == "get_file_summary":
                result = handler(params.get("file_path", ""))
            elif method in {"list_hotspots", "list_by_blast_radius", "list_refactor_candidates"}:
                result = handler(int(params.get("n", 10)))
            else:
                result = handler()
            return {"jsonrpc": "2.0", "id": req_id, "result": result}
        except Exception as exc:  # noqa: BLE001
            log.error("MCP dispatch error [%s]: %s", method, exc)
            return {"jsonrpc": "2.0", "id": req_id,
                    "error": {"code": -32603, "message": str(exc)}}

    def serve_stdio(self) -> None:
        log.info("MCP v8 server listening on stdio (JSON-RPC 2.0, newline-delimited)")
        for raw_line in sys.stdin:
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                req = json.loads(raw_line)
            except json.JSONDecodeError as exc:
                resp: dict[str, Any] = {
                    "jsonrpc": "2.0", "id": None,
                    "error": {"code": -32700, "message": f"Parse error: {exc}"},
                }
            else:
                resp = self._dispatch(req)
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()
