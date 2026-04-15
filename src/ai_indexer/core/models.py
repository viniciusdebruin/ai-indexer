"""Core data models for the AI Context Indexer.

Uses dataclasses with __slots__ (Python 3.10+ `slots=True`) for memory
efficiency when processing 10k+ file projects.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ConfidenceValue:
    """A labelled value paired with a detection confidence score [0, 1]."""

    value: str
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {"value": self.value, "confidence": self.confidence}


@dataclass(slots=True)
class FileMetadata:
    """Full metadata record for a single analysed source file."""

    # ── Identity ────────────────────────────────────────────────────────────
    file: str
    file_type: ConfidenceValue
    domain: ConfidenceValue
    secondary_domain: str | None
    layer: str
    criticality: str
    entrypoint: bool

    # ── Complexity ──────────────────────────────────────────────────────────
    complexity_label: str
    complexity_score: int
    priority_score: int
    priority_breakdown: dict[str, float]

    # ── Narrative ───────────────────────────────────────────────────────────
    context: str
    role_hint: str

    # ── Capabilities ────────────────────────────────────────────────────────
    capabilities: dict[str, list[str]]

    # ── Dependency graph ────────────────────────────────────────────────────
    dependencies: list[str]
    internal_dependencies: list[str]
    fan_in: int = 0
    fan_out: int = 0
    pagerank: float = 0.0

    # ── Architecture health ─────────────────────────────────────────────────
    warnings: list[str] = field(default_factory=list)
    is_in_cycle: bool = False
    impact_radius: int = 0

    # ── Documentation & types ───────────────────────────────────────────────
    docstrings: dict[str, str] = field(default_factory=dict)
    type_hints: dict[str, dict[str, str]] = field(default_factory=dict)
    chunks: list[str] = field(default_factory=list)
    module_doc: str | None = None

    # ── Semantic hints (AI consumer-facing) ─────────────────────────────────
    hints: dict[str, Any] = field(default_factory=dict)

    # ── v8 Derived metrics ───────────────────────────────────────────────────
    refactor_effort: float = 0.0
    """(complexity_score / (fan_in + 1)) * |log(pagerank + ε)|
    High value → expensive to safely refactor; low → easy to touch."""

    blast_radius: int = 0
    """Quantitative 2nd-degree impact: number of distinct files reachable
    within 2 hops in the reverse dependency graph."""

    # ── Serialisation ────────────────────────────────────────────────────────
    def to_dict(self, compact: bool = True) -> dict[str, Any]:
        if compact:
            return {
                "f":   self.file,
                "ft":  self.file_type.to_dict(),
                "d":   self.domain.to_dict(),
                "sd":  self.secondary_domain,
                "l":   self.layer[0] if self.layer else "u",
                "c":   self.criticality[0],
                "ep":  self.entrypoint,
                "cl":  self.complexity_label[0],
                "cs":  self.complexity_score,
                "ps":  self.priority_score,
                "pb":  self.priority_breakdown,
                "cx":  self.context,
                "rh":  self.role_hint,
                "caps": {k: v[:5] for k, v in self.capabilities.items() if v},
                "deps":  self.dependencies[:10],
                "ideps": self.internal_dependencies[:10],
                "fi":  self.fan_in,
                "fo":  self.fan_out,
                "pr":  round(self.pagerank, 5),
                "warns": self.warnings,
                "cyc": self.is_in_cycle,
                "ir":  self.impact_radius,
                "re":  round(self.refactor_effort, 4),
                "br":  self.blast_radius,
                "docs": self.docstrings,
                "th":  self.type_hints,
                "hints": self.hints,
                "chunks": self.chunks,
            }
        d = {
            "file": self.file,
            "file_type": self.file_type.to_dict(),
            "domain": self.domain.to_dict(),
            "secondary_domain": self.secondary_domain,
            "layer": self.layer,
            "criticality": self.criticality,
            "entrypoint": self.entrypoint,
            "complexity_label": self.complexity_label,
            "complexity_score": self.complexity_score,
            "priority_score": self.priority_score,
            "priority_breakdown": self.priority_breakdown,
            "context": self.context,
            "role_hint": self.role_hint,
            "capabilities": self.capabilities,
            "dependencies": self.dependencies,
            "internal_dependencies": self.internal_dependencies,
            "fan_in": self.fan_in,
            "fan_out": self.fan_out,
            "pagerank": self.pagerank,
            "warnings": self.warnings,
            "is_in_cycle": self.is_in_cycle,
            "impact_radius": self.impact_radius,
            "refactor_effort": self.refactor_effort,
            "blast_radius": self.blast_radius,
            "docstrings": self.docstrings,
            "type_hints": self.type_hints,
            "module_doc": self.module_doc,
            "hints": self.hints,
            "chunks": self.chunks,
        }
        return d


def compute_refactor_effort(
    complexity_score: int,
    fan_in: int,
    pagerank: float,
) -> float:
    """(complexity_score / (fan_in + 1)) * |log(pagerank + ε)|

    Interpretation:
    - High complexity + many dependents + high centrality → hard to refactor
    - Low complexity + few dependents → easy to touch
    """
    eps = 1e-9
    return (complexity_score / (fan_in + 1)) * abs(math.log(pagerank + eps))


def compute_blast_radius_2hop(
    node: str,
    reverse_graph: dict[str, list[str]],
) -> int:
    """Count distinct files that transitively depend on *node* up to 2 hops.

    Uses the reverse dependency graph (fan-in direction).
    """
    visited: set[str] = set()
    frontier = reverse_graph.get(node, [])
    for dep in frontier:
        visited.add(dep)
        for dep2 in reverse_graph.get(dep, []):
            visited.add(dep2)
    return len(visited)
