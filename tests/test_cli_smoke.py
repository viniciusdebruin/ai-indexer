from __future__ import annotations

import sys
from pathlib import Path

import pytest

import ai_indexer.main as cli
from ai_indexer.core.models import ConfidenceValue, FileMetadata


def test_cli_writes_json_output(tmp_path: Path, monkeypatch) -> None:
    def fake_run(self, on_progress=None) -> None:  # noqa: ANN001
        file_meta = FileMetadata(
            file="src/app.py",
            file_type=ConfidenceValue("module", 0.9),
            domain=ConfidenceValue("core", 0.8),
            secondary_domain=None,
            layer="application",
            criticality="supporting",
            entrypoint=True,
            complexity_label="low",
            complexity_score=10,
            priority_score=5,
            priority_breakdown={"criticality": 1.0},
            context="",
            role_hint="",
            capabilities={"functions": [], "classes": [], "exports": []},
            dependencies=[],
            internal_dependencies=[],
            warnings=[],
            is_in_cycle=False,
            docstrings={},
            type_hints={},
            chunks=[],
            module_doc=None,
            hints={},
        )
        self.files = {file_meta.file: file_meta}
        self.graph = {file_meta.file: []}
        self.rev = {file_meta.file: []}

    monkeypatch.setattr(cli.AnalysisEngine, "run", fake_run)
    monkeypatch.setattr(cli.AnalysisUI, "header", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli.AnalysisUI, "on_progress", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli.AnalysisUI, "stop_progress", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli.AnalysisUI, "show_summary", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli.AnalysisUI, "error", lambda *args, **kwargs: None)

    monkeypatch.setattr(sys, "argv", ["ai-indexer", "--format", "json", str(tmp_path)])

    cli.main()

    assert (tmp_path / "estrutura_projeto.json").exists()


def test_cli_honors_output_override(tmp_path: Path, monkeypatch) -> None:
    captured: dict[str, Path | None] = {}

    def fake_run(self, on_progress=None) -> None:  # noqa: ANN001
        file_meta = FileMetadata(
            file="src/app.py",
            file_type=ConfidenceValue("module", 0.9),
            domain=ConfidenceValue("core", 0.8),
            secondary_domain=None,
            layer="application",
            criticality="supporting",
            entrypoint=True,
            complexity_label="low",
            complexity_score=10,
            priority_score=5,
            priority_breakdown={"criticality": 1.0},
            context="",
            role_hint="",
            capabilities={"functions": [], "classes": [], "exports": []},
            dependencies=[],
            internal_dependencies=[],
            warnings=[],
            is_in_cycle=False,
            docstrings={},
            type_hints={},
            chunks=[],
            module_doc=None,
            hints={},
        )
        self.files = {file_meta.file: file_meta}
        self.graph = {file_meta.file: []}
        self.rev = {file_meta.file: []}

    def fake_write_outputs(engine, output_data, fmt, override_path, out_dir):  # noqa: ANN001
        captured["override"] = override_path
        return [("json", out_dir / "estrutura_projeto.json")]

    monkeypatch.setattr(cli.AnalysisEngine, "run", fake_run)
    monkeypatch.setattr(cli.AnalysisUI, "header", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli.AnalysisUI, "on_progress", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli.AnalysisUI, "stop_progress", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli.AnalysisUI, "show_summary", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli.AnalysisUI, "error", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli, "_write_outputs", fake_write_outputs)
    override = tmp_path / "custom.json"
    monkeypatch.setattr(sys, "argv", ["ai-indexer", "--format", "json", "--output", str(override), str(tmp_path)])

    cli.main()

    assert captured["override"] == override


def test_cli_summary_only_skips_writing(tmp_path: Path, monkeypatch) -> None:
    def fake_run(self, on_progress=None) -> None:  # noqa: ANN001
        file_meta = FileMetadata(
            file="src/app.py",
            file_type=ConfidenceValue("module", 0.9),
            domain=ConfidenceValue("core", 0.8),
            secondary_domain=None,
            layer="application",
            criticality="supporting",
            entrypoint=True,
            complexity_label="low",
            complexity_score=10,
            priority_score=5,
            priority_breakdown={"criticality": 1.0},
            context="",
            role_hint="",
            capabilities={"functions": [], "classes": [], "exports": []},
            dependencies=[],
            internal_dependencies=[],
            warnings=[],
            is_in_cycle=False,
            docstrings={},
            type_hints={},
            chunks=[],
            module_doc=None,
            hints={},
        )
        self.files = {file_meta.file: file_meta}
        self.graph = {file_meta.file: []}
        self.rev = {file_meta.file: []}

    def boom(*args, **kwargs):  # noqa: ANN001
        raise AssertionError("_write_outputs should not be called in summary-only mode")

    monkeypatch.setattr(cli.AnalysisEngine, "run", fake_run)
    monkeypatch.setattr(cli.AnalysisUI, "header", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli.AnalysisUI, "on_progress", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli.AnalysisUI, "stop_progress", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli.AnalysisUI, "show_summary", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli.AnalysisUI, "error", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli, "_write_outputs", boom)
    monkeypatch.setattr(sys, "argv", ["ai-indexer", "--summary-only", str(tmp_path)])

    cli.main()


def test_cli_validate_config(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / ".indexer.yaml").write_text("output_dir: out\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["ai-indexer", "--validate-config", str(tmp_path)])

    with pytest.raises(SystemExit) as excinfo:
        cli.main()
    assert excinfo.value.code == 0


def test_cli_fail_on_warning_exits_nonzero(tmp_path: Path, monkeypatch) -> None:
    def fake_run(self, on_progress=None) -> None:  # noqa: ANN001
        file_meta = FileMetadata(
            file="src/app.py",
            file_type=ConfidenceValue("module", 0.9),
            domain=ConfidenceValue("core", 0.8),
            secondary_domain=None,
            layer="application",
            criticality="supporting",
            entrypoint=True,
            complexity_label="low",
            complexity_score=10,
            priority_score=5,
            priority_breakdown={"criticality": 1.0},
            context="",
            role_hint="",
            capabilities={"functions": [], "classes": [], "exports": []},
            dependencies=[],
            internal_dependencies=[],
            warnings=["general warning"],
            is_in_cycle=False,
            docstrings={},
            type_hints={},
            chunks=[],
            module_doc=None,
            hints={},
        )
        self.files = {file_meta.file: file_meta}
        self.graph = {file_meta.file: []}
        self.rev = {file_meta.file: []}

    monkeypatch.setattr(cli.AnalysisEngine, "run", fake_run)
    monkeypatch.setattr(cli.AnalysisUI, "header", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli.AnalysisUI, "on_progress", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli.AnalysisUI, "stop_progress", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli.AnalysisUI, "show_summary", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli.AnalysisUI, "error", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli, "_write_outputs", lambda *args, **kwargs: [])
    monkeypatch.setattr(sys, "argv", ["ai-indexer", "--fail-on-warning", str(tmp_path)])

    with pytest.raises(SystemExit) as excinfo:
        cli.main()
    assert excinfo.value.code == 2


def test_cli_fail_on_secret_exits_nonzero(tmp_path: Path, monkeypatch) -> None:
    def fake_run(self, on_progress=None) -> None:  # noqa: ANN001
        file_meta = FileMetadata(
            file="src/app.py",
            file_type=ConfidenceValue("module", 0.9),
            domain=ConfidenceValue("core", 0.8),
            secondary_domain=None,
            layer="application",
            criticality="supporting",
            entrypoint=True,
            complexity_label="low",
            complexity_score=10,
            priority_score=5,
            priority_breakdown={"criticality": 1.0},
            context="",
            role_hint="",
            capabilities={"functions": [], "classes": [], "exports": []},
            dependencies=[],
            internal_dependencies=[],
            warnings=["hardcoded secret"],
            is_in_cycle=False,
            docstrings={},
            type_hints={},
            chunks=[],
            module_doc=None,
            hints={},
        )
        self.files = {file_meta.file: file_meta}
        self.graph = {file_meta.file: []}
        self.rev = {file_meta.file: []}

    monkeypatch.setattr(cli.AnalysisEngine, "run", fake_run)
    monkeypatch.setattr(cli.AnalysisUI, "header", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli.AnalysisUI, "on_progress", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli.AnalysisUI, "stop_progress", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli.AnalysisUI, "show_summary", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli.AnalysisUI, "error", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli, "_write_outputs", lambda *args, **kwargs: [])
    monkeypatch.setattr(sys, "argv", ["ai-indexer", "--fail-on-secret", str(tmp_path)])

    with pytest.raises(SystemExit) as excinfo:
        cli.main()
    assert excinfo.value.code == 2


def test_analysis_profile_fast_adjusts_config() -> None:
    config = cli._apply_profile(cli.load_config(Path(".")), "fast")

    assert config.max_depth <= 4
    assert config.chunk_max_tokens <= 400


def test_cli_diagnostics_prints_json(tmp_path: Path, monkeypatch, capsys) -> None:
    def fake_run(self, on_progress=None) -> None:  # noqa: ANN001
        file_meta = FileMetadata(
            file="src/app.py",
            file_type=ConfidenceValue("module", 0.9),
            domain=ConfidenceValue("core", 0.8),
            secondary_domain=None,
            layer="application",
            criticality="supporting",
            entrypoint=True,
            complexity_label="low",
            complexity_score=10,
            priority_score=5,
            priority_breakdown={"criticality": 1.0},
            context="",
            role_hint="",
            capabilities={"functions": [], "classes": [], "exports": []},
            dependencies=[],
            internal_dependencies=[],
            warnings=[],
            is_in_cycle=False,
            docstrings={},
            type_hints={},
            chunks=[],
            module_doc=None,
            hints={},
        )
        self.files = {file_meta.file: file_meta}
        self.graph = {file_meta.file: []}
        self.rev = {file_meta.file: []}

    monkeypatch.setattr(cli.AnalysisEngine, "run", fake_run)
    monkeypatch.setattr(cli.AnalysisUI, "header", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli.AnalysisUI, "on_progress", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli.AnalysisUI, "stop_progress", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli.AnalysisUI, "show_summary", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli.AnalysisUI, "error", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli, "_write_outputs", lambda *args, **kwargs: [])
    monkeypatch.setattr(sys, "argv", ["ai-indexer", "--diagnostics", "--summary-only", str(tmp_path)])

    cli.main()

    stdout = capsys.readouterr().out
    assert '"analysis_mode": "full"' in stdout
