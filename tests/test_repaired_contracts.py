from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from xml.etree import ElementTree as ET

from ai_indexer import __version__ as package_version
from ai_indexer.core.engine import AnalysisEngine
from ai_indexer.core.models import ConfidenceValue, FileMetadata
from ai_indexer.exporters.html import HtmlExporter
from ai_indexer.exporters.xml_exporter import XmlExporter
from ai_indexer.audio_tours.script_builder import ScriptBuilder
from ai_indexer.main import _build_output
from ai_indexer.tours.generator import TourGenerator
from ai_indexer.utils.config import IndexerConfig
from ai_indexer.utils.config import load_config, validate_config


def _make_file() -> FileMetadata:
    return FileMetadata(
        file="src/app.py",
        file_type=ConfidenceValue("module", 0.9),
        domain=ConfidenceValue("billing", 0.8),
        secondary_domain=None,
        layer="application",
        criticality="critical",
        entrypoint=True,
        complexity_label="medium",
        complexity_score=240,
        priority_score=88,
        priority_breakdown={"criticality": 30.0},
        context="",
        role_hint="main entrypoint",
        capabilities={"functions": ["main"], "classes": [], "exports": []},
        dependencies=["requests"],
        internal_dependencies=["src/db.py"],
        warnings=[],
        is_in_cycle=False,
        docstrings={},
        type_hints={},
        chunks=[],
        module_doc="Application entrypoint.",
        hints={},
    )


def test_version_is_centralized() -> None:
    assert package_version == "0.0.5"


def test_build_output_uses_package_version(tmp_path: Path) -> None:
    engine = AnalysisEngine(tmp_path, IndexerConfig({}))
    file_meta = _make_file()
    engine.files = {file_meta.file: file_meta}
    engine.graph = {file_meta.file: []}
    engine.rev = {file_meta.file: []}  # type: ignore[assignment]

    output = _build_output(engine)

    assert output["version"] == package_version
    assert output["stats"]["critical_files"] == 1
    assert output["diagnostics"]["security_scan_enabled"] is True
    assert "optional_dependencies" in output["diagnostics"]


def test_html_exporter_normalizes_compact_fields() -> None:
    exporter = HtmlExporter()
    context = exporter._build_context(
        {
            "version": package_version,
            "project": "demo",
            "stats": {"total_files": 1, "critical_files": 1, "domains": 1, "entrypoints": 1},
            "files": {
                "src/app.py": {
                    "f": "src/app.py",
                    "d": {"value": "billing"},
                    "c": "c",
                    "ep": True,
                    "ps": 88,
                    "fi": 1,
                    "rh": "main entrypoint",
                    "warns": ["warning"],
                    "re": 2.5,
                    "br": 3,
                }
            },
            "dependency_graph": {"src/app.py": []},
            "reverse_graph": {"src/app.py": []},
            "modules": {},
            "hotspots": [],
        }
    )

    assert context["stats"]["critical"] == 1
    assert context["all_files"]["src/app.py"]["criticality"] == "critical"


def test_xml_exporter_normalizes_compact_fields(tmp_path: Path) -> None:
    exporter = XmlExporter()
    output_path = tmp_path / "analysis.xml"
    exporter.export(
        {
            "version": package_version,
            "project": "demo",
            "generated_at": "2026-04-17T00:00:00Z",
            "stats": {"total_files": 1, "critical_files": 1, "domains": 1, "entrypoints": 1},
            "files": {
                "src/app.py": {
                    "f": "src/app.py",
                    "d": {"value": "billing"},
                    "c": "c",
                    "ep": True,
                    "ps": 88,
                    "fi": 1,
                    "module_doc": "Application entrypoint.",
                    "caps": {"functions": ["main"], "classes": [], "exports": []},
                    "internal_dependencies": ["src/db.py"],
                    "warns": ["warning"],
                }
            },
            "hotspots": [
                {
                    "file": "src/app.py",
                    "priority_score": 88,
                    "pagerank": 0.1,
                    "fan_in": 1,
                    "refactor_effort": 2.5,
                    "blast_radius": 3,
                }
            ],
        },
        output_path,
    )

    root = ET.parse(output_path).getroot()
    file_node = root.find("./files/file")
    assert root.find("./file_summary").attrib["critical"] == "1"
    assert file_node is not None
    assert file_node.attrib["criticality"] == "critical"
    assert file_node.findtext("module_doc") == "Application entrypoint."
    assert file_node.findtext("./dependencies/dep") == "src/db.py"


def test_tour_generator_uses_domain_value(tmp_path: Path) -> None:
    file_meta = _make_file()
    engine = SimpleNamespace(files={file_meta.file: file_meta}, root=tmp_path)

    tour = TourGenerator(engine).generate_overview_tour()

    assert "billing" in tour.steps[0].explanation or "billing" in tour.steps[-1].explanation
    assert any(step.title == "Resumo Arquitetural" for step in tour.steps)


def test_script_builder_cleans_and_orders_tour_text() -> None:
    file_meta = _make_file()
    engine = SimpleNamespace(files={file_meta.file: file_meta}, root=Path("demo"))
    tour = TourGenerator(engine).generate_overview_tour()

    script = ScriptBuilder().build_full_script(tour)

    assert "Ponto de Entrada Principal" in script or "Resumo Arquitetural" in script
    assert "dunder" not in script
    assert "ponto pái" in script or "ponto pai" in script


def test_subinterpreter_path_falls_back_to_serial(tmp_path: Path) -> None:
    engine = AnalysisEngine(tmp_path, IndexerConfig({}))
    results = engine._run_subinterpreters(
        [tmp_path / "a.py", tmp_path / "b.py"],
        lambda p: (p.name, {"file": p.name}),
    )

    assert results == [("a.py", {"file": "a.py"}), ("b.py", {"file": "b.py"})]


def test_load_config_handles_non_mapping(tmp_path: Path) -> None:
    (tmp_path / ".indexer.yaml").write_text("- bad\n- config\n", encoding="utf-8")

    config = load_config(tmp_path)
    valid, message = validate_config(tmp_path)

    assert config.output_dir == "."
    assert valid is False
    assert "mapping" in message
