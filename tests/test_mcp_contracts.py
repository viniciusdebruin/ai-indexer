from __future__ import annotations

from ai_indexer.core.models import ConfidenceValue, FileMetadata
from ai_indexer.mcp.server import MCPServer


def _file(name: str, fan_in: int = 0, priority: int = 10, funcs: list[str] | None = None) -> FileMetadata:
    return FileMetadata(
        file=name,
        file_type=ConfidenceValue("module", 0.9),
        domain=ConfidenceValue("core", 0.8),
        secondary_domain=None,
        layer="application",
        criticality="supporting",
        entrypoint=False,
        complexity_label="low",
        complexity_score=10,
        priority_score=priority,
        priority_breakdown={"criticality": 1.0},
        context="",
        role_hint="",
        capabilities={"functions": funcs or ["run"], "classes": [], "exports": []},
        dependencies=["dep.py"],
        internal_dependencies=["dep.py"],
        fan_in=fan_in,
        fan_out=1,
        pagerank=0.25,
        warnings=[],
        is_in_cycle=False,
        docstrings={},
        type_hints={},
        chunks=[],
        module_doc=None,
        hints={"description": "demo"},
        refactor_effort=2.0,
        blast_radius=3,
    )


def test_mcp_query_contracts() -> None:
    files = {
        "src/app.py": _file("src/app.py", fan_in=2, priority=99),
        "src/dep.py": _file("src/dep.py", fan_in=1, priority=10, funcs=["helper"]),
        "src/orphan.py": _file("src/orphan.py", fan_in=0, priority=1, funcs=["noop"]),
    }
    server = MCPServer(
        files,
        {"src/app.py": ["src/dep.py"], "src/dep.py": ["src/app.py"]},
        {"src/app.py": ["src/dep.py"], "src/dep.py": ["src/app.py"]},
        git_context={"change_frequency": {"src/app.py": 7, "src/dep.py": 3}},
    )

    assert server.get_dependents("src/app.py") == ["src/dep.py"]
    assert server.search_symbol("run") == [{"file": "src/app.py", "symbols": ["run"]}]

    summary = server.get_file_summary("src/app.py")
    assert summary is not None
    assert summary["file"] == "src/app.py"
    assert summary["domain"] == "core"

    assert server.list_hotspots(1)[0]["file"] == "src/app.py"
    assert server.list_orphans() == ["src/orphan.py"]
    assert server.list_by_blast_radius(1)[0]["blast_radius"] == 3
    assert server.list_refactor_candidates(1)[0]["refactor_effort"] == 2.0
    assert server.explain_score("src/app.py")["priority_score"] == 99
    assert server.get_subgraph("src/app.py", depth=1)["nodes"] == ["src/app.py", "src/dep.py"]
    assert server.get_dependency_chain("src/app.py", "src/dep.py") == ["src/app.py", "src/dep.py"]
    assert server.list_cycles() == [["src/app.py", "src/dep.py"]]
    assert server.list_by_volatility(1)[0] == {"file": "src/app.py", "changes": 7}


def test_mcp_filters_and_pagination() -> None:
    files = {
        "src/app.py": _file("src/app.py", priority=90),
        "src/billing.py": _file("src/billing.py", priority=80),
        "src/log.py": _file("src/log.py", priority=10),
    }
    files["src/app.py"].domain = ConfidenceValue("core", 0.8)
    files["src/billing.py"].domain = ConfidenceValue("billing", 0.9)
    files["src/log.py"].warnings = ["warning"]
    server = MCPServer(files, {}, {})

    assert [item["file"] for item in server.list_hotspots(n=1, offset=1)] == ["src/billing.py"]
    assert [item["file"] for item in server.list_hotspots(domain="billing")] == ["src/billing.py"]
    assert [item["file"] for item in server.list_hotspots(warnings_only=True)] == ["src/log.py"]


def test_mcp_dispatch_unknown_method() -> None:
    server = MCPServer({}, {}, {})
    response = server._dispatch({"id": 1, "method": "missing"})

    assert response["error"]["code"] == -32601
