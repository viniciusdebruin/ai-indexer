"""Canonical normalization helpers for analysis outputs."""

from __future__ import annotations

from typing import Any

_CRIT_MAP = {
    "c": "critical",
    "i": "infra",
    "f": "config",
    "s": "supporting",
}

_LAYER_MAP = {
    "p": "presentation",
    "a": "application",
    "d": "domain",
    "i": "infrastructure",
    "u": "unknown",
}


def normalize_file_payload(fd: dict[str, Any], fallback_path: str = "") -> dict[str, Any]:
    file_path = str(fd.get("f") or fd.get("file") or fallback_path)
    file_type = fd.get("ft") or fd.get("file_type") or {}
    domain = fd.get("d") or fd.get("domain") or {}
    criticality = _criticality_value(fd)
    layer = _layer_value(fd)
    caps = fd.get("caps") or fd.get("capabilities") or {}
    warns = fd.get("warns") or fd.get("warnings") or []
    return {
        "file": file_path,
        "file_type": _confidence_value(file_type),
        "domain": _confidence_value(domain),
        "secondary_domain": fd.get("sd") or fd.get("secondary_domain"),
        "layer": layer,
        "criticality": criticality,
        "entrypoint": bool(fd.get("ep") or fd.get("entrypoint")),
        "complexity_label": fd.get("cl") or fd.get("complexity_label") or "low",
        "complexity_score": int(fd.get("cs") or fd.get("complexity_score") or 0),
        "priority_score": int(fd.get("ps") or fd.get("priority_score") or 0),
        "priority_breakdown": fd.get("pb") or fd.get("priority_breakdown") or {},
        "context": fd.get("cx") or fd.get("context") or "",
        "role_hint": fd.get("rh") or fd.get("role_hint") or "",
        "capabilities": _capabilities_value(caps),
        "dependencies": list(fd.get("deps") or fd.get("dependencies") or []),
        "internal_dependencies": list(fd.get("ideps") or fd.get("internal_dependencies") or []),
        "fan_in": int(fd.get("fi") or fd.get("fan_in") or 0),
        "fan_out": int(fd.get("fo") or fd.get("fan_out") or 0),
        "pagerank": float(fd.get("pr") or fd.get("pagerank") or 0.0),
        "warnings": list(warns),
        "is_in_cycle": bool(fd.get("cyc") or fd.get("is_in_cycle")),
        "impact_radius": int(fd.get("ir") or fd.get("impact_radius") or 0),
        "refactor_effort": float(fd.get("re") or fd.get("refactor_effort") or 0.0),
        "blast_radius": int(fd.get("br") or fd.get("blast_radius") or 0),
        "docstrings": fd.get("docs") or fd.get("docstrings") or {},
        "type_hints": fd.get("th") or fd.get("type_hints") or {},
        "module_doc": fd.get("module_doc"),
        "hints": fd.get("hints") or {},
        "chunks": list(fd.get("chunks") or []),
    }


def _confidence_value(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        if "value" in raw and "confidence" in raw:
            return {"value": raw.get("value", ""), "confidence": raw.get("confidence", 0.0)}
    return {"value": "", "confidence": 0.0}


def _criticality_value(fd: dict[str, Any]) -> str:
    raw = fd.get("criticality")
    if isinstance(raw, str) and raw:
        return raw
    short = fd.get("c")
    if isinstance(short, str) and short:
        return _CRIT_MAP.get(short, short)
    return "supporting"


def _layer_value(fd: dict[str, Any]) -> str:
    raw = fd.get("layer")
    if isinstance(raw, str) and raw:
        return raw
    short = fd.get("l")
    if isinstance(short, str) and short:
        return _LAYER_MAP.get(short, short)
    return "unknown"


def _capabilities_value(caps: dict[str, Any]) -> dict[str, list[str]]:
    return {
        "functions": list(caps.get("fn") or caps.get("functions") or []),
        "classes": list(caps.get("cl") or caps.get("classes") or []),
        "exports": list(caps.get("ex") or caps.get("exports") or []),
    }


def validate_output_payload(data: dict[str, Any], fmt: str) -> None:
    required = {"version", "project", "generated_at"}
    missing = [key for key in required if key not in data]
    if missing:
        raise ValueError(f"Missing required output keys: {', '.join(sorted(missing))}")

    if fmt in {"json", "toon", "xml", "html"} and "files" not in data:
        raise ValueError(f"{fmt} output requires a 'files' section")
    if fmt in {"json", "toon", "xml", "html"} and "stats" not in data:
        raise ValueError(f"{fmt} output requires a 'stats' section")
    if fmt == "html" and "dependency_graph" not in data:
        raise ValueError("html output requires dependency graph data")
    if fmt == "xml" and "hotspots" not in data:
        raise ValueError("xml output requires hotspots data")
