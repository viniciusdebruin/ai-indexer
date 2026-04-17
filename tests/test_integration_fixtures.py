from __future__ import annotations

from pathlib import Path

from ai_indexer.core.engine import AnalysisEngine
from ai_indexer.utils.config import IndexerConfig


def test_python_src_layout_import_resolution(tmp_path: Path) -> None:
    pkg = tmp_path / "src" / "demoapp"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "service.py").write_text("def run() -> str:\n    return 'ok'\n", encoding="utf-8")
    (pkg / "main.py").write_text("from demoapp.service import run\n\nprint(run())\n", encoding="utf-8")

    engine = AnalysisEngine(tmp_path, IndexerConfig({}))
    engine.run()

    assert "src/demoapp/main.py" in engine.files
    assert "src/demoapp/service.py" in engine.files["src/demoapp/main.py"].internal_dependencies


def test_typescript_workspace_alias_resolution(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text('{"workspaces":["packages/*"]}', encoding="utf-8")
    app = tmp_path / "packages" / "web"
    (app / "src" / "lib").mkdir(parents=True)
    (app / "package.json").write_text('{"name":"web"}', encoding="utf-8")
    (app / "tsconfig.json").write_text(
        '{"compilerOptions":{"baseUrl":"src","paths":{"@lib/*":["lib/*"]}}}',
        encoding="utf-8",
    )
    (app / "src" / "lib" / "util.ts").write_text("export const meaning = 42;\n", encoding="utf-8")
    (app / "src" / "main.ts").write_text("import { meaning } from '@lib/util';\nconsole.log(meaning);\n", encoding="utf-8")

    engine = AnalysisEngine(app, IndexerConfig({}))
    engine.run()

    assert "src/main.ts" in engine.files
    assert "src/lib/util.ts" in engine.files["src/main.ts"].internal_dependencies


def test_mixed_language_fixture_runs_with_security_findings(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "app.py").write_text("API_KEY = 'AIza123456789012345678901234567890123'\n", encoding="utf-8")
    (src / "widget.ts").write_text("export function widget() { return 'ok'; }\n", encoding="utf-8")

    engine = AnalysisEngine(tmp_path, IndexerConfig({}))
    engine.run()

    warnings = engine.files["src/app.py"].warnings
    assert any("secret" in warning.lower() for warning in warnings)
    assert "src/widget.ts" in engine.files
