"""MCP (Model Context Protocol) server - JSON-RPC 2.0 over stdio."""

from __future__ import annotations

import fnmatch
import json
import logging
import sys
from collections import deque
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ai_indexer.core.models import FileMetadata

log = logging.getLogger("ai-indexer.mcp")


class MCPServer:
    """Serve targeted queries against an analysed project index via JSON-RPC 2.0."""

    def __init__(
        self,
        files: dict[str, "FileMetadata"],
        graph: dict[str, list[str]],
        reverse_graph: dict[str, list[str]],
        git_context: dict[str, Any] | None = None,
    ) -> None:
        self._files = files
        self._graph = graph
        self._rev = reverse_graph
        self._git_context = git_context or {}

    def get_dependents(self, file_path: str) -> list[str]:
        return list(self._rev.get(file_path, []))

    def search_symbol(self, symbol_name: str) -> list[dict[str, Any]]:
        needle = symbol_name.lower()
        hits: list[dict[str, Any]] = []
        for path, fd in self._files.items():
            caps = fd.capabilities
            all_sym: list[str] = caps.get("functions", []) + caps.get("classes", []) + caps.get("exports", [])
            matched = [s for s in all_sym if needle in s.lower()]
            if matched:
                hits.append({"file": path, "symbols": matched[:10]})
        return hits

    def get_file_summary(self, file_path: str) -> dict[str, Any] | None:
        fd = self._files.get(file_path)
        if fd is None:
            return None
        return {
            "file": fd.file,
            "hints": fd.hints,
            "module_doc": fd.module_doc,
            "file_type": fd.file_type.value,
            "domain": fd.domain.value,
            "layer": fd.layer,
            "criticality": fd.criticality,
            "entrypoint": fd.entrypoint,
            "complexity_label": fd.complexity_label,
            "complexity_score": fd.complexity_score,
            "priority_score": fd.priority_score,
            "fan_in": fd.fan_in,
            "fan_out": fd.fan_out,
            "pagerank": round(fd.pagerank, 5),
            "refactor_effort": round(fd.refactor_effort, 4),
            "blast_radius": fd.blast_radius,
            "dependencies": fd.dependencies[:10],
            "internal_dependencies": fd.internal_dependencies[:10],
            "warnings": fd.warnings,
            "capabilities": {k: v[:8] for k, v in fd.capabilities.items() if v},
        }

    def list_hotspots(
        self,
        n: int = 10,
        offset: int = 0,
        domain: str | None = None,
        criticality: str | None = None,
        layer: str | None = None,
        warnings_only: bool = False,
    ) -> list[dict[str, Any]]:
        files = self._filter_files(domain=domain, criticality=criticality, layer=layer, warnings_only=warnings_only)
        return [
            {
                "file": fd.file,
                "priority_score": fd.priority_score,
                "pagerank": round(fd.pagerank, 5),
                "fan_in": fd.fan_in,
                "domain": fd.domain.value,
                "criticality": fd.criticality,
                "refactor_effort": round(fd.refactor_effort, 4),
                "blast_radius": fd.blast_radius,
                "score_explanation": fd.priority_breakdown,
            }
            for fd in sorted(files, key=lambda f: f.priority_score, reverse=True)[offset:offset + n]
        ]

    def list_orphans(self, offset: int = 0, limit: int = 50) -> list[str]:
        orphans = [
            fd.file for fd in self._files.values()
            if fd.fan_in == 0
            and not fd.entrypoint
            and fd.file_type.value not in {"docs", "config", "asset", "template"}
        ]
        return orphans[offset:offset + limit]

    def list_by_blast_radius(
        self,
        n: int = 10,
        offset: int = 0,
        domain: str | None = None,
    ) -> list[dict[str, Any]]:
        files = self._filter_files(domain=domain)
        return [
            {"file": fd.file, "blast_radius": fd.blast_radius, "fan_in": fd.fan_in}
            for fd in sorted(files, key=lambda f: f.blast_radius, reverse=True)[offset:offset + n]
        ]

    def list_refactor_candidates(
        self,
        n: int = 10,
        offset: int = 0,
        criticality: str | None = None,
    ) -> list[dict[str, Any]]:
        files = self._filter_files(criticality=criticality)
        return [
            {
                "file": fd.file,
                "refactor_effort": round(fd.refactor_effort, 4),
                "complexity_score": fd.complexity_score,
                "fan_in": fd.fan_in,
            }
            for fd in sorted(files, key=lambda f: f.refactor_effort, reverse=True)[offset:offset + n]
        ]

    def get_subgraph(self, file_path: str, depth: int = 1) -> dict[str, Any]:
        nodes = self._walk_graph(file_path, depth)
        edges = [
            [src, dst]
            for src in sorted(nodes)
            for dst in self._graph.get(src, [])
            if dst in nodes
        ]
        return {"root": file_path, "depth": depth, "nodes": sorted(nodes), "edges": edges}

    def get_dependency_chain(self, source: str, target: str, direction: str = "outbound") -> list[str]:
        graph = self._graph if direction != "inbound" else self._rev
        queue: deque[tuple[str, list[str]]] = deque([(source, [source])])
        seen = {source}
        while queue:
            node, path = queue.popleft()
            if node == target:
                return path
            for nxt in graph.get(node, []):
                if nxt not in seen:
                    seen.add(nxt)
                    queue.append((nxt, path + [nxt]))
        return []

    def explain_score(self, file_path: str) -> dict[str, Any] | None:
        fd = self._files.get(file_path)
        if fd is None:
            return None
        return {
            "file": fd.file,
            "priority_score": fd.priority_score,
            "criticality": fd.criticality,
            "complexity_label": fd.complexity_label,
            "fan_in": fd.fan_in,
            "fan_out": fd.fan_out,
            "pagerank": round(fd.pagerank, 5),
            "blast_radius": fd.blast_radius,
            "priority_breakdown": fd.priority_breakdown,
            "warnings": fd.warnings,
            "hints": fd.hints,
        }

    def list_cycles(self) -> list[list[str]]:
        return [sorted(component) for component in self._strongly_connected_components() if len(component) > 1]

    def list_by_volatility(self, n: int = 10, offset: int = 0) -> list[dict[str, Any]]:
        freq = self._git_context.get("change_frequency", {})
        ranked = sorted(freq.items(), key=lambda item: item[1], reverse=True)
        return [{"file": file_path, "changes": count} for file_path, count in ranked[offset:offset + n]]

    _METHODS: dict[str, str] = {
        "get_dependents": "get_dependents",
        "search_symbol": "search_symbol",
        "get_file_summary": "get_file_summary",
        "list_hotspots": "list_hotspots",
        "list_orphans": "list_orphans",
        "list_by_blast_radius": "list_by_blast_radius",
        "list_refactor_candidates": "list_refactor_candidates",
        "get_subgraph": "get_subgraph",
        "get_dependency_chain": "get_dependency_chain",
        "explain_score": "explain_score",
        "list_cycles": "list_cycles",
        "list_by_volatility": "list_by_volatility",
    }

    def _dispatch(self, req: dict[str, Any]) -> dict[str, Any]:
        req_id = req.get("id")
        method = req.get("method", "")
        params = req.get("params") or {}
        attr = self._METHODS.get(method)
        if attr is None:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Method not found: {method!r}"},
            }
        try:
            handler = getattr(self, attr)
            result = handler(**params) if isinstance(params, dict) else handler()
            return {"jsonrpc": "2.0", "id": req_id, "result": result}
        except TypeError as exc:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32602, "message": f"Invalid params: {exc}"},
            }
        except Exception as exc:  # noqa: BLE001
            log.error("MCP dispatch error [%s]: %s", method, exc)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32603, "message": str(exc)},
            }

    def serve_stdio(self) -> None:
        log.info("MCP server listening on stdio (JSON-RPC 2.0)")
        for raw_line in sys.stdin:
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                req = json.loads(raw_line)
            except json.JSONDecodeError as exc:
                resp: dict[str, Any] = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": f"Parse error: {exc}"},
                }
            else:
                resp = self._dispatch(req)
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()

    def _filter_files(
        self,
        domain: str | None = None,
        criticality: str | None = None,
        layer: str | None = None,
        warnings_only: bool = False,
        file_glob: str | None = None,
    ) -> list["FileMetadata"]:
        filtered: list["FileMetadata"] = []
        for fd in self._files.values():
            if domain and fd.domain.value != domain:
                continue
            if criticality and fd.criticality != criticality:
                continue
            if layer and fd.layer != layer:
                continue
            if warnings_only and not fd.warnings:
                continue
            if file_glob and not fnmatch.fnmatch(fd.file, file_glob):
                continue
            filtered.append(fd)
        return filtered

    def _walk_graph(self, file_path: str, depth: int) -> set[str]:
        visited: set[str] = set()
        queue: deque[tuple[str, int]] = deque([(file_path, 0)])
        while queue:
            node, level = queue.popleft()
            if node in visited or level > depth:
                continue
            visited.add(node)
            for nxt in self._graph.get(node, []):
                queue.append((nxt, level + 1))
            for nxt in self._rev.get(node, []):
                queue.append((nxt, level + 1))
        return visited

    def _strongly_connected_components(self) -> list[set[str]]:
        index = 0
        stack: list[str] = []
        indices: dict[str, int] = {}
        lowlinks: dict[str, int] = {}
        on_stack: set[str] = set()
        components: list[set[str]] = []

        def strongconnect(node: str) -> None:
            nonlocal index
            indices[node] = index
            lowlinks[node] = index
            index += 1
            stack.append(node)
            on_stack.add(node)

            for nxt in self._graph.get(node, []):
                if nxt not in indices:
                    strongconnect(nxt)
                    lowlinks[node] = min(lowlinks[node], lowlinks[nxt])
                elif nxt in on_stack:
                    lowlinks[node] = min(lowlinks[node], indices[nxt])

            if lowlinks[node] == indices[node]:
                component: set[str] = set()
                while True:
                    popped = stack.pop()
                    on_stack.remove(popped)
                    component.add(popped)
                    if popped == node:
                        break
                components.append(component)

        for node in self._graph:
            if node not in indices:
                strongconnect(node)
        return components
