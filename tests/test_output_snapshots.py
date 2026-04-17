from __future__ import annotations

from pathlib import Path

from ai_indexer.core.models import ConfidenceValue, FileMetadata
from ai_indexer.core.engine import AnalysisEngine
from ai_indexer.main import _build_output, _write_outputs
from ai_indexer.utils.config import IndexerConfig


def _file() -> FileMetadata:
    return FileMetadata(
        file="src/app.py",
        file_type=ConfidenceValue("module", 0.9),
        domain=ConfidenceValue("billing", 0.8),
        secondary_domain=None,
        layer="application",
        criticality="critical",
        entrypoint=True,
        complexity_label="medium",
        complexity_score=120,
        priority_score=77,
        priority_breakdown={"criticality": 30.0},
        context="",
        role_hint="main entrypoint",
        capabilities={"functions": ["main"], "classes": [], "exports": []},
        dependencies=[],
        internal_dependencies=[],
        warnings=["secret found"],
        is_in_cycle=False,
        docstrings={},
        type_hints={},
        chunks=[],
        module_doc="Application entrypoint.",
        hints={"description": "App entrypoint."},
        refactor_effort=1.5,
        blast_radius=2,
    )


def test_exported_formats_are_stable(tmp_path: Path) -> None:
    engine = AnalysisEngine(tmp_path, IndexerConfig({}))
    file_meta = _file()
    engine.files = {file_meta.file: file_meta}
    engine.graph = {file_meta.file: []}
    engine.rev = {file_meta.file: []}  # type: ignore[assignment]

    output = _build_output(engine)
    outputs = _write_outputs(engine, output, "all", None, tmp_path)

    names = {path.name for _fmt, path in outputs}
    assert names == {
        "estrutura_projeto.toon",
        "estrutura_projeto.json",
        "estrutura_projeto.html",
        "estrutura_projeto.md",
        "estrutura_projeto.xml",
    }
    assert "\"project\":" in (tmp_path / "estrutura_projeto.json").read_text(encoding="utf-8")
    assert "<ai_index" in (tmp_path / "estrutura_projeto.xml").read_text(encoding="utf-8")
    assert "files:" in (tmp_path / "estrutura_projeto.toon").read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in (tmp_path / "estrutura_projeto.html").read_text(encoding="utf-8")
    assert "# AI Context Index" in (tmp_path / "estrutura_projeto.md").read_text(encoding="utf-8")
