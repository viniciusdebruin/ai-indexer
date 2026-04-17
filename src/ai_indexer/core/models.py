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


@dataclass(slots=True)
class AnalysisRecord:
    """Stable internal analysis record stored before FileMetadata hydration."""

    file: str
    file_type: ConfidenceValue
    domain: ConfidenceValue
    secondary_domain: str | None
    layer: str
    criticality: str
    entrypoint: bool
    complexity_label: str
    complexity_score: int
    capabilities: dict[str, list[str]]
    dependencies: list[str]
    internal_dependencies: list[str]
    warnings: list[str] = field(default_factory=list)
    is_in_cycle: bool = False
    docstrings: dict[str, str] = field(default_factory=dict)
    type_hints: dict[str, dict[str, str]] = field(default_factory=dict)
    chunks: list[str] = field(default_factory=list)
    module_doc: str | None = None
    hints: dict[str, Any] = field(default_factory=dict)
    refactor_effort: float = 0.0
    blast_radius: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "file_type": self.file_type.to_dict(),
            "domain": self.domain.to_dict(),
            "secondary_domain": self.secondary_domain,
            "layer": self.layer,
            "criticality": self.criticality,
            "entrypoint": self.entrypoint,
            "complexity_label": self.complexity_label,
            "complexity_score": self.complexity_score,
            "capabilities": self.capabilities,
            "dependencies": self.dependencies,
            "internal_dependencies": self.internal_dependencies,
            "warnings": self.warnings,
            "is_in_cycle": self.is_in_cycle,
            "docstrings": self.docstrings,
            "type_hints": self.type_hints,
            "chunks": self.chunks,
            "module_doc": self.module_doc,
            "hints": self.hints,
            "refactor_effort": self.refactor_effort,
            "blast_radius": self.blast_radius,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AnalysisRecord":
        return cls(
            file=str(data["file"]),
            file_type=_coerce_confidence(data.get("file_type")),
            domain=_coerce_confidence(data.get("domain")),
            secondary_domain=data.get("secondary_domain"),
            layer=str(data.get("layer", "unknown")),
            criticality=str(data.get("criticality", "supporting")),
            entrypoint=bool(data.get("entrypoint", False)),
            complexity_label=str(data.get("complexity_label", "low")),
            complexity_score=int(data.get("complexity_score", 0)),
            capabilities=_coerce_capabilities(data.get("capabilities")),
            dependencies=_coerce_str_list(data.get("dependencies")),
            internal_dependencies=_coerce_str_list(data.get("internal_dependencies")),
            warnings=_coerce_str_list(data.get("warnings")),
            is_in_cycle=bool(data.get("is_in_cycle", False)),
            docstrings=_coerce_str_map(data.get("docstrings")),
            type_hints=_coerce_nested_str_map(data.get("type_hints")),
            chunks=_coerce_str_list(data.get("chunks")),
            module_doc=str(data["module_doc"]) if data.get("module_doc") is not None else None,
            hints=dict(data.get("hints") or {}),
            refactor_effort=float(data.get("refactor_effort", 0.0)),
            blast_radius=int(data.get("blast_radius", 0)),
        )


@dataclass(frozen=True, slots=True)
class ProjectStats:
    total_files: int
    critical_files: int
    entrypoints: int
    domains: int

    def to_dict(self) -> dict[str, int]:
        return {
            "total_files": self.total_files,
            "critical_files": self.critical_files,
            "entrypoints": self.entrypoints,
            "domains": self.domains,
        }


@dataclass(frozen=True, slots=True)
class HotspotRecord:
    file: str
    priority_score: int
    pagerank: float
    fan_in: int
    refactor_effort: float
    blast_radius: int
    domain: str
    criticality: str
    score_explanation: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "priority_score": self.priority_score,
            "pagerank": self.pagerank,
            "fan_in": self.fan_in,
            "refactor_effort": round(self.refactor_effort, 4),
            "blast_radius": self.blast_radius,
            "domain": self.domain,
            "criticality": self.criticality,
            "score_explanation": self.score_explanation,
        }


@dataclass(slots=True)
class ProjectAnalysis:
    version: str
    project: str
    generated_at: str
    stats: ProjectStats
    files: dict[str, FileMetadata]
    dependency_graph: dict[str, list[str]]
    reverse_graph: dict[str, list[str]]
    pagerank: dict[str, float]
    execution_flows: list[Any]
    modules: dict[str, list[str]]
    hotspots: list[HotspotRecord]
    instruction: str = ""
    git_context: dict[str, Any] | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "version": self.version,
            "project": self.project,
            "generated_at": self.generated_at,
            "stats": self.stats.to_dict(),
            "files": {path: fd.to_dict(compact=True) for path, fd in sorted(self.files.items())},
            "dependency_graph": self.dependency_graph,
            "reverse_graph": self.reverse_graph,
            "pagerank": self.pagerank,
            "execution_flows": self.execution_flows,
            "modules": self.modules,
            "hotspots": [hotspot.to_dict() for hotspot in self.hotspots],
            "diagnostics": self.diagnostics,
        }
        if self.instruction:
            payload["instruction"] = self.instruction
        if self.git_context:
            payload["git_context"] = self.git_context
        return payload


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


def _coerce_confidence(raw: Any) -> ConfidenceValue:
    if isinstance(raw, ConfidenceValue):
        return raw
    if isinstance(raw, dict):
        return ConfidenceValue(
            value=str(raw.get("value", "")),
            confidence=float(raw.get("confidence", 0.0)),
        )
    return ConfidenceValue(value="", confidence=0.0)


def _coerce_str_list(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [str(item) for item in raw]


def _coerce_str_map(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    return {str(key): str(value) for key, value in raw.items()}


def _coerce_nested_str_map(raw: Any) -> dict[str, dict[str, str]]:
    if not isinstance(raw, dict):
        return {}
    nested: dict[str, dict[str, str]] = {}
    for key, value in raw.items():
        if isinstance(value, dict):
            nested[str(key)] = {str(inner_key): str(inner_value) for inner_key, inner_value in value.items()}
    return nested


def _coerce_capabilities(raw: Any) -> dict[str, list[str]]:
    if not isinstance(raw, dict):
        return {"functions": [], "classes": [], "exports": []}
    return {
        "functions": _coerce_str_list(raw.get("functions")),
        "classes": _coerce_str_list(raw.get("classes")),
        "exports": _coerce_str_list(raw.get("exports")),
    }
