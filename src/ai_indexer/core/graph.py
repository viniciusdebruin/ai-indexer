"""Graph construction and scoring helpers."""

from __future__ import annotations

from collections import defaultdict, deque
from pathlib import Path

from ai_indexer.core.models import FileMetadata, compute_blast_radius_2hop, compute_refactor_effort


def build_graph(
    files: dict[str, FileMetadata],
    file_index: dict[str, str],
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    graph: dict[str, list[str]] = {}
    rev: defaultdict[str, list[str]] = defaultdict(list)

    for fd in files.values():
        resolved_set: set[str] = set()
        for dep in fd.internal_dependencies:
            canon = canonicalize(dep, files, file_index)
            if canon and canon != fd.file:
                resolved_set.add(canon)
        resolved = list(resolved_set)
        graph[fd.file] = resolved
        fd.internal_dependencies = resolved
        fd.fan_out = len(resolved)

    for src, tgts in graph.items():
        for tgt in tgts:
            rev[tgt].append(src)

    for fd in files.values():
        fd.fan_in = len(rev.get(fd.file, []))

    return graph, dict(rev)


def canonicalize(dep: str, files: dict[str, FileMetadata], file_index: dict[str, str]) -> str | None:
    if dep in files:
        return dep
    if dep in file_index:
        return file_index[dep]
    stem = Path(dep).stem
    if stem in file_index:
        return file_index[stem]
    return None


def enrich_graph_metrics(files: dict[str, FileMetadata], graph: dict[str, list[str]]) -> None:
    pagerank = compute_pagerank(graph)
    for fd in files.values():
        fd.pagerank = pagerank.get(fd.file, 0.0)
        fd.impact_radius = impact_radius(graph, fd.file, depth=2) if fd.fan_out > 0 else 0


def compute_v8_metrics(files: dict[str, FileMetadata], rev: dict[str, list[str]]) -> None:
    for fd in files.values():
        fd.refactor_effort = compute_refactor_effort(fd.complexity_score, fd.fan_in, fd.pagerank)
        fd.blast_radius = compute_blast_radius_2hop(fd.file, rev)


def detect_cycles(graph: dict[str, list[str]]) -> set[str]:
    index = 0
    stack: list[str] = []
    indices: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    on_stack: set[str] = set()
    cycle_nodes: set[str] = set()

    def strongconnect(v: str) -> None:
        nonlocal index
        indices[v] = lowlinks[v] = index
        index += 1
        stack.append(v)
        on_stack.add(v)

        for w in graph.get(v, []):
            if w not in indices:
                strongconnect(w)
                lowlinks[v] = min(lowlinks[v], lowlinks[w])
            elif w in on_stack:
                lowlinks[v] = min(lowlinks[v], indices[w])

        if lowlinks[v] == indices[v]:
            comp: list[str] = []
            while True:
                w = stack.pop()
                on_stack.remove(w)
                comp.append(w)
                if w == v:
                    break
            if len(comp) > 1:
                cycle_nodes.update(comp)

    for node in graph:
        if node not in indices:
            strongconnect(node)
    return cycle_nodes


def compute_pagerank(graph: dict[str, list[str]], d: float = 0.85, iters: int = 30, tol: float = 1e-6) -> dict[str, float]:
    nodes = list(graph.keys())
    n = len(nodes)
    if not n:
        return {}
    out_deg = {node: len(nbs) for node, nbs in graph.items()}
    in_map: dict[str, list[str]] = defaultdict(list)
    for src, tgts in graph.items():
        for tgt in tgts:
            in_map[tgt].append(src)
    dangling = {node for node in nodes if out_deg[node] == 0}
    pr = {node: 1.0 / n for node in nodes}
    for _ in range(iters):
        total_d = sum(pr[node] for node in dangling)
        new_pr: dict[str, float] = {}
        for node in nodes:
            score = (1.0 - d) / n + d * (total_d / n)
            for src in in_map.get(node, []):
                score += d * (pr[src] / max(1, out_deg[src]))
            new_pr[node] = score
        diff = sum(abs(new_pr[v] - pr[v]) for v in nodes)
        pr = new_pr
        if diff < tol:
            break
    total = sum(pr.values()) or 1.0
    return {k: v / total for k, v in pr.items()}


def impact_radius(graph: dict[str, list[str]], node: str, depth: int = 2) -> int:
    visited: set[str] = set()
    q: deque[tuple[str, int]] = deque([(node, 0)])
    count = 0
    while q:
        cur, dist = q.popleft()
        if cur in visited or dist > depth:
            continue
        visited.add(cur)
        if cur != node:
            count += 1
        for nxt in graph.get(cur, []):
            if nxt not in visited:
                q.append((nxt, dist + 1))
    return count


