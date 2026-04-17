"""Analysis engine orchestrating parsing, graph metrics, scoring, and contexts."""

from __future__ import annotations

import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, TypedDict
from collections.abc import Callable

from ai_indexer.core.architecture import apply_architecture_rules
from ai_indexer.core.cache import AnalysisCache
from ai_indexer.core.classification import (
    complexity as classify_complexity,
    complexity_signals as classify_complexity_signals,
    criticality_signals as classify_criticality_signals,
    detect_domain as classify_domain,
    detect_layer as classify_layer,
    detect_type as classify_type,
    extract_hints as classify_hints,
    get_criticality as classify_criticality,
    is_entrypoint as classify_entrypoint,
    domain_evidence as classify_domain_evidence,
)
from ai_indexer.core.context_builder import build_contexts
from ai_indexer.core.graph import build_graph, compute_v8_metrics, enrich_graph_metrics
from ai_indexer.core.models import AnalysisRecord, FileMetadata
from ai_indexer.core.pipeline import AnalysisPipeline
from ai_indexer.core.scoring import finalize_scores
from ai_indexer.parsers.base import ParserRegistry
from ai_indexer.parsers.python import PythonParser
from ai_indexer.parsers.typescript import TypeScriptParser
from ai_indexer.utils.config import IndexerConfig
from ai_indexer.utils.io import ImportResolver, safe_read_text
from ai_indexer.version import __version__

log = logging.getLogger("ai-indexer.engine")
sys.setrecursionlimit(10000)

_IGNORE_DIRS: frozenset[str] = frozenset({
    ".git", ".hg", ".svn", "node_modules", "vendor", "bower_components", "jspm_packages",
    "dist", "build", "out", "target", "bin", "obj", "Debug", "Release", "x64", "x86",
    "generated", ".output", ".nuxt", ".next", ".turbo",
    "__pycache__", ".venv", "venv", "env", ".env", "virtualenv", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", ".tox", "*.egg-info",
    ".gradle", ".idea", ".settings", "classes", ".classpath", ".project",
    "packages", ".vs", ".bundle", "log", "tmp", "coverage",
    "storage", "bootstrap/cache", ".vscode", ".cursor", ".claude", ".fleet", ".eclipse",
    ".nyc_output", "test-results", "reports", ".terraform", ".serverless", "cdk.out", ".amplify",
    "docs/_build", "site", ".docusaurus", "data", "dataset", "models", "uploads", "static",
})
_IGNORE_PATTERNS: tuple[str, ...] = (
    ".DS_Store", "Thumbs.db", "desktop.ini", "ehthumbs.db",
    ".env*", "*.local", "*.secret", ".git*", "*.patch",
    "*.lock", "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock",
    "Pipfile.lock", "Gemfile.lock", "Cargo.lock", "composer.lock", "mix.lock", "pubspec.lock",
    "*.min.js", "*.min.css", "*.min.js.map", "*.min.css.map",
    "*.pyc", "*.pyo", "*.pyd", "*.so", "*.dll", "*.exe", "*.o", "*.a",
    "*.class", "*.jar", "*.war", "*.ear", "*.png", "*.jpg", "*.jpeg", "*.gif", "*.ico",
    "*.svg", "*.webp", "*.woff", "*.woff2", "*.ttf", "*.eot", "*.otf",
    "*.mp3", "*.mp4", "*.wav", "*.avi", "*.mov", "*.webm",
    "*.zip", "*.tar", "*.gz", "*.bz2", "*.7z", "*.rar", "*.pdf", "*.doc", "*.docx",
    "*.xls", "*.xlsx", "*.ppt", "*.pptx", "*.pem", "*.crt", "*.key", "*.p12", "*.pfx",
    "*.log", "*.bak", "*.tmp", "*.swp", "*.swo",
)
_GENERATED_FILES: frozenset[str] = frozenset({
    "estrutura_projeto.json", "estrutura_projeto.toon", "estrutura_projeto.html",
    "estrutura_projeto.md", ".aicontext_cache_v6.json", ".aicontext_cache_v8.json",
    "package-lock.json", "yarn.lock", "Cargo.lock", "go.sum",
})
_TEXT_SUFFIXES: frozenset[str] = frozenset({
    ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts",
    ".py", ".pyi", ".pyx", ".pxd", ".pxi",
    ".html", ".htm", ".xhtml", ".vue", ".svelte", ".astro", ".css", ".scss", ".sass",
    ".less", ".styl", ".rb", ".erb", ".rake", ".gemspec", ".php", ".phtml", ".php3", ".php4",
    ".php5", ".phps", ".java", ".kt", ".kts", ".scala", ".groovy", ".c", ".h", ".cpp", ".hpp",
    ".cc", ".hh", ".cxx", ".hxx", ".rs", ".zig", ".cs", ".fs", ".vb", ".go", ".sh", ".bash",
    ".zsh", ".fish", ".ps1", ".psm1", ".psd1", ".json", ".jsonc", ".json5", ".yml", ".yaml",
    ".toml", ".ini", ".cfg", ".conf", ".config", ".properties", ".env", ".env.example",
    ".md", ".markdown", ".rst", ".adoc", ".tex", ".txt", "", ".sql", ".graphql", ".gql",
    ".prisma", ".proto", ".thrift", ".dart", ".ex", ".exs", ".elm", ".purs", ".hs", ".lhs",
    ".clj", ".cljs", ".edn", ".rkt", ".lisp", ".lsp", ".swift", ".m", ".mm",
})
_SPECIAL_TEXT_FILENAMES: frozenset[str] = frozenset({
    "Dockerfile", "Makefile", "Procfile", "Gemfile", "Rakefile", "Vagrantfile", "Berksfile",
    "Cheffile", "Puppetfile", "Jenkinsfile", "Brewfile", "Fastfile", "Podfile", "Cargo.toml",
    "Cargo.lock", "go.mod", "go.sum", "CMakeLists.txt", "BUILD", "WORKSPACE", "BUCK",
    "requirements.txt", "Pipfile", "pyproject.toml", "package.json", "package-lock.json",
    "yarn.lock", "pnpm-lock.yaml", "tsconfig.json", "jsconfig.json", "babel.config.js",
    "webpack.config.js", ".eslintrc", ".prettierrc", ".stylelintrc", ".editorconfig",
    ".gitignore", ".dockerignore", ".npmignore", ".eslintignore", "README", "LICENSE",
    "CHANGELOG", "CONTRIBUTING", "CODE_OF_CONDUCT",
})


class _MetaTemplate(TypedDict):
    file: str
    file_type: dict[str, Any]
    domain: dict[str, Any]
    secondary_domain: str | None
    layer: str
    criticality: str
    entrypoint: bool
    complexity_label: str
    complexity_score: int
    capabilities: dict[str, list[str]]
    dependencies: list[str]
    internal_dependencies: list[str]
    warnings: list[str]
    is_in_cycle: bool
    docstrings: dict[str, str]
    type_hints: dict[str, dict[str, str]]
    chunks: list[str]
    module_doc: str | None
    hints: dict[str, Any]
    refactor_effort: float
    blast_radius: int


_EMPTY_META_TEMPLATE: _MetaTemplate = {
    "file": "",
    "file_type": {"value": "module", "confidence": 0.3},
    "domain": {"value": "core", "confidence": 0.3},
    "secondary_domain": None,
    "layer": "unknown",
    "criticality": "supporting",
    "entrypoint": False,
    "complexity_label": "low",
    "complexity_score": 0,
    "capabilities": {"functions": [], "classes": [], "exports": []},
    "dependencies": [],
    "internal_dependencies": [],
    "warnings": [],
    "is_in_cycle": False,
    "docstrings": {},
    "type_hints": {},
    "chunks": [],
    "module_doc": None,
    "hints": {},
    "refactor_effort": 0.0,
    "blast_radius": 0,
}

_INTERPRETERS_AVAILABLE = False


class AnalysisEngine:
    """Orchestrates the full analysis pipeline for a project root."""

    def __init__(self, root: Path, config: IndexerConfig) -> None:
        if not root.is_dir():
            raise ValueError(f"Root must be an existing directory: {root}")
        self.root = root
        self.config = config
        self.cache = AnalysisCache(root)
        self.files: dict[str, FileMetadata] = {}
        self.graph: dict[str, list[str]] = {}
        self.rev: dict[str, list[str]] = {}
        self.ignore_dirs = _IGNORE_DIRS | self.config.exclude_dirs
        self.ignore_patterns = _IGNORE_PATTERNS + self.config.exclude_patterns
        self.generated_files = _GENERATED_FILES
        self.text_suffixes = _TEXT_SUFFIXES
        self.special_text_filenames = _SPECIAL_TEXT_FILENAMES | self.config.extra_text_filenames
        self._file_index: dict[str, str] = {}
        self._registry = ParserRegistry()
        self._register_default_parsers()

    def _register_default_parsers(self) -> None:
        self._registry.register(PythonParser())
        self._registry.register(TypeScriptParser())

    def run(self, on_progress: Callable[[int, int], None] | None = None) -> None:
        t0 = time.time()
        log.info("AI Context Indexer v%s - %s", __version__, self.root)
        try:
            AnalysisPipeline(self).run(on_progress=on_progress)
        except KeyboardInterrupt:
            log.warning("Interrupted - saving partial cache")
            self.cache.save()
            raise
        elapsed = time.time() - t0
        log.info("Analysed %d files in %.2fs", len(self.files), elapsed)

    def _update_files_and_cache(self, results: list[tuple[str, AnalysisRecord | dict[str, Any]]]) -> None:
        for rel, record in results:
            normalized = record if isinstance(record, AnalysisRecord) else AnalysisRecord.from_dict(record)
            self.cache.set(self.root / rel, normalized.to_dict())
            self.files[rel] = self._meta_to_model(normalized)
        self.cache.save()

    def _post_process(self) -> None:
        self.graph, self.rev = build_graph(self.files, self._file_index)
        enrich_graph_metrics(self.files, self.graph)
        compute_v8_metrics(self.files, self.rev)
        apply_architecture_rules(self.files, self.graph)
        finalize_scores(self.files)
        build_contexts(self.files)

    def _analyse_parallel(
        self,
        paths: list[Path],
        aliases: dict[str, Path],
        bare: set[str],
        max_workers: int,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> list[tuple[str, AnalysisRecord | dict[str, Any]]]:
        results: list[tuple[str, AnalysisRecord | dict[str, Any]]] = []
        total = len(paths)
        done = 0

        def work(path: Path) -> tuple[str, AnalysisRecord | dict[str, Any]]:
            rel = path.relative_to(self.root).as_posix()
            cached = self.cache.get(path)
            if cached:
                return rel, cached
            resolver = ImportResolver(self.root, self._file_index, aliases, bare)
            return rel, self._analyse_file(path, resolver)

        if _INTERPRETERS_AVAILABLE and len(paths) > 8:
            try:
                return self._run_subinterpreters(paths, work)
            except Exception as exc:  # noqa: BLE001
                log.warning("Sub-interpreter failed: %s, falling back to threads", exc)

        try:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(work, path): path for path in paths}
                for future in as_completed(futures):
                    try:
                        results.append(future.result())
                    except Exception as exc:  # noqa: BLE001
                        log.error("Worker error for %s: %s", futures[future], exc)
                    done += 1
                    if on_progress:
                        on_progress(done, total)
        except Exception as exc:  # noqa: BLE001
            log.error("ThreadPool failed: %s, using serial processing", exc)
            for path in paths:
                results.append(work(path))
                done += 1
                if on_progress:
                    on_progress(done, total)
        return results

    def _run_subinterpreters(
        self,
        paths: list[Path],
        work_func: Callable[[Path], tuple[str, AnalysisRecord | dict[str, Any]]],
    ) -> list[tuple[str, AnalysisRecord | dict[str, Any]]]:
        return [work_func(path) for path in paths]

    def _analyse_file(self, path: Path, resolver: ImportResolver) -> AnalysisRecord:
        try:
            src = safe_read_text(path)
        except Exception as exc:  # noqa: BLE001
            log.warning("Cannot read %s: %s", path, exc)
            return self._empty_meta(path)

        rel = path.relative_to(self.root)
        parsed = self._registry.parse(path, src, resolver)
        warnings: list[str] = []
        if self.config.security_enabled:
            try:
                from ai_indexer.utils.security import scan_secrets
                warnings.extend(scan_secrets(path, src))
            except Exception as exc:  # noqa: BLE001
                log.debug("Secret scan failed for %s: %s", path, exc)

        file_type = classify_type(rel, src, self.config)
        symbols = parsed.functions + parsed.classes + parsed.exports
        domain_scores = classify_domain_evidence(
            rel,
            src,
            dependencies=parsed.external + parsed.internal,
            symbols=symbols,
            module_doc=parsed.module_doc,
        )
        domain, secondary_domain = classify_domain(
            rel,
            src,
            self.config,
            dependencies=parsed.external + parsed.internal,
            symbols=symbols,
            module_doc=parsed.module_doc,
        )
        layer = classify_layer(file_type.value, rel, src)
        entrypoint = classify_entrypoint(rel, src)
        criticality_signals = classify_criticality_signals(
            rel,
            file_type.value,
            domain=domain.value,
            entrypoint=entrypoint,
            dependencies=parsed.external + parsed.internal,
            warnings=warnings,
        )
        criticality = classify_criticality(
            rel,
            file_type.value,
            self.config,
            domain=domain.value,
            entrypoint=entrypoint,
            dependencies=parsed.external + parsed.internal,
            warnings=warnings,
        )
        complexity_score, complexity_label = classify_complexity(
            parsed.lines,
            parsed.functions,
            parsed.classes,
            parsed.internal,
            src,
        )
        complexity_signals = classify_complexity_signals(
            parsed.lines,
            parsed.functions,
            parsed.classes,
            parsed.internal,
            src,
        )
        hints = classify_hints(
            rel,
            src,
            file_type.value,
            domain.value,
            parsed.functions,
            parsed.classes,
            parsed.external + parsed.internal,
            parsed.module_doc,
            domain_scores=domain_scores,
            criticality_scores=criticality_signals,
            complexity_scores=complexity_signals,
            complexity_label=complexity_label,
        )

        return AnalysisRecord(
            file=rel.as_posix(),
            file_type=file_type,
            domain=domain,
            secondary_domain=secondary_domain,
            layer=layer,
            criticality=criticality,
            entrypoint=entrypoint,
            complexity_label=complexity_label,
            complexity_score=complexity_score,
            capabilities={"functions": parsed.functions, "classes": parsed.classes, "exports": parsed.exports},
            dependencies=parsed.external,
            internal_dependencies=parsed.internal,
            warnings=warnings,
            is_in_cycle=False,
            docstrings=parsed.docstrings,
            type_hints=parsed.type_hints,
            chunks=parsed.chunks,
            module_doc=parsed.module_doc,
            hints=hints,
            refactor_effort=0.0,
            blast_radius=0,
        )

    def _meta_to_model(self, record: AnalysisRecord | dict[str, Any]) -> FileMetadata:
        normalized = record if isinstance(record, AnalysisRecord) else AnalysisRecord.from_dict(record)
        return FileMetadata(
            file=normalized.file,
            file_type=normalized.file_type,
            domain=normalized.domain,
            secondary_domain=normalized.secondary_domain,
            layer=normalized.layer,
            criticality=normalized.criticality,
            entrypoint=normalized.entrypoint,
            complexity_label=normalized.complexity_label,
            complexity_score=normalized.complexity_score,
            priority_score=0,
            priority_breakdown={},
            context="",
            role_hint="",
            capabilities=normalized.capabilities,
            dependencies=normalized.dependencies,
            internal_dependencies=normalized.internal_dependencies,
            warnings=normalized.warnings,
            is_in_cycle=normalized.is_in_cycle,
            docstrings=normalized.docstrings,
            type_hints=normalized.type_hints,
            chunks=normalized.chunks,
            module_doc=normalized.module_doc,
            hints=normalized.hints,
            refactor_effort=normalized.refactor_effort,
            blast_radius=normalized.blast_radius,
        )

    def _empty_meta(self, path: Path) -> AnalysisRecord:
        rel = path.relative_to(self.root).as_posix()
        payload = dict(_EMPTY_META_TEMPLATE)
        payload["file"] = rel
        return AnalysisRecord.from_dict(payload)
