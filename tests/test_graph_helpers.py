from __future__ import annotations

from ai_indexer.core.graph import (
    build_graph,
    compute_pagerank,
    compute_v8_metrics,
    detect_cycles,
    impact_radius,
)
from ai_indexer.core.models import ConfidenceValue, FileMetadata


def _file(name: str, deps: list[str] | None = None) -> FileMetadata:
    return FileMetadata(
        file=name,
        file_type=ConfidenceValue("module", 0.9),
        domain=ConfidenceValue("core", 0.8),
        secondary_domain=None,
        layer="application",
        criticality="supporting",
        entrypoint=False,
        complexity_label="low",
        complexity_score=100,
        priority_score=20,
        priority_breakdown={"criticality": 10.0},
        context="",
        role_hint="",
        capabilities={"functions": [], "classes": [], "exports": []},
        dependencies=deps or [],
        internal_dependencies=deps or [],
        warnings=[],
        is_in_cycle=False,
        docstrings={},
        type_hints={},
        chunks=[],
        module_doc=None,
        hints={},
    )


def test_build_graph_canonicalizes_dependencies() -> None:
    files = {
        "src/app.py": _file("src/app.py", ["helper", "src/utils/helper.py"]),
        "src/utils/helper.py": _file("src/utils/helper.py"),
    }
    file_index = {"helper": "src/utils/helper.py", "src/utils/helper.py": "src/utils/helper.py"}

    graph, rev = build_graph(files, file_index)

    assert graph["src/app.py"] == ["src/utils/helper.py"]
    assert files["src/app.py"].fan_out == 1
    assert files["src/utils/helper.py"].fan_in == 1
    assert rev["src/utils/helper.py"] == ["src/app.py"]


def test_graph_metrics_and_cycle_detection() -> None:
    graph = {
        "a.py": ["b.py"],
        "b.py": ["c.py"],
        "c.py": ["a.py"],
    }
    files = {name: _file(name, deps=deps) for name, deps in graph.items()}
    for fd in files.values():
        fd.internal_dependencies = list(fd.dependencies)
    built_graph, rev = build_graph(files, {"a.py": "a.py", "b.py": "b.py", "c.py": "c.py"})

    pagerank = compute_pagerank(built_graph)
    compute_v8_metrics(files, rev)

    assert round(sum(pagerank.values()), 6) == 1.0
    assert detect_cycles(built_graph) == {"a.py", "b.py", "c.py"}
    assert impact_radius(built_graph, "a.py") == 2
    assert all(fd.refactor_effort > 0 for fd in files.values())
    assert all(fd.blast_radius >= 0 for fd in files.values())
