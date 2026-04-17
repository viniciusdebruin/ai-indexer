"""CLI entrypoint for AI Context Indexer."""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ai_indexer.core.engine import AnalysisEngine
from ai_indexer.core.models import HotspotRecord, ProjectAnalysis, ProjectStats
from ai_indexer.exporters.html import HtmlExporter
from ai_indexer.exporters.toon import ToonExporter
from ai_indexer.exporters.xml_exporter import XmlExporter
from ai_indexer.core.output import validate_output_payload
from ai_indexer.mcp.server import MCPServer
from ai_indexer.utils.config import load_config, validate_config
from ai_indexer.utils.ui import AnalysisUI
from ai_indexer.version import __version__

# ── Structured JSON logging (active only in verbose/non-TTY mode) ─────────────
logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","msg":"%(message)s"}',
    datefmt="%Y-%m-%dT%H:%M:%S",
    stream=sys.stderr,
)
log = logging.getLogger("ai-indexer")


# ── Argument parser ───────────────────────────────────────────────────────────

_DESCRIPTION = f"""\
AI Context Indexer v{__version__} — Analyze a project directory and generate
structured metadata optimized for LLM consumption.

The indexer parses source files (Python, TypeScript/JavaScript, and more),
builds a dependency graph, computes PageRank-based priority scores, detects
architectural hotspots, scans for leaked credentials, and exports the results
in multiple formats. Output files are written to the project root (or the
directory set by 'output_dir' in .indexer.yaml).
"""

_EPILOG = """\
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT FILES  (written to project root unless --output or output_dir is set)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  estrutura_projeto.json   Full analysis as compact JSON (all metadata)
  estrutura_projeto.toon   Compact TOON format — ~50% fewer tokens than JSON,
                           ideal for pasting directly into an LLM context window
  estrutura_projeto.html   Interactive 3-D nebula dashboard (opens in browser)
  estrutura_projeto.md     Markdown summary with hotspot table and warnings
  estrutura_projeto.xml    XML format recommended by Anthropic for Claude;
                           includes <instruction>, <hotspots>, <files>, <git_context>
  .aicontext_cache_v8.json Per-file cache keyed by path:mtime:size (not committed)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONFIGURATION FILE  (.indexer.yaml in the project root — all fields optional)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  # File selection
  exclude_dirs: ["scripts", "legacy"]     # skip these directory names anywhere
  exclude_patterns: ["*.generated.ts"]    # skip files matching these globs
  include_patterns: ["src/**/*.py"]       # whitelist — only index matching files
                                          # (empty = include everything)

  # Analysis
  max_depth: 8                            # max directory traversal depth
  max_workers: 0                          # 0 = auto (cpu_count × 2), or fixed int
  chunk_max_tokens: 800                   # max tokens per code chunk

  # Output
  output_dir: "."                         # where to write output files
  output_formats: ["toon", "html", "md"]  # default formats when using --format all

  # Overrides
  criticality_overrides:
    "src/core/engine.py": "critical"
  domain_overrides:
    "src/legacy/": "backend"

  # Instruction injection (same as --instruction-file)
  instruction_file: "AGENTS.md"

  # Security scanning
  security:
    enabled: true                         # set false to disable secret detection

  # Git context (disabled by default)
  git:
    include_logs: true                    # include recent commit log
    logs_count: 10                        # number of commits to include
    include_diffs: false                  # include HEAD diff stat
    sort_by_changes: false                # collect per-file change frequency
    sort_max_commits: 100                 # how many commits to look back

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXAMPLES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  # Index current directory, produce all output formats
  ai-indexer

  # Index a specific project
  ai-indexer ~/projects/my-app

  # Generate only the XML file (best for pasting into Claude)
  ai-indexer --format xml ~/projects/my-app

  # Generate only TOON (most token-efficient for LLMs)
  ai-indexer --format toon --output context.toon ~/projects/my-app

  # Inject a custom instruction into every output
  ai-indexer --instruction-file AGENTS.md --format xml

  # Include git history (last 20 commits) in the output
  ai-indexer --format json   # after setting git.include_logs: true in .indexer.yaml

  # Force full re-analysis (ignore cache)
  ai-indexer --no-cache

  # Start MCP server after indexing (for IDE / agent integrations)
  ai-indexer --mcp ~/projects/my-app

  # Generate an offline audio tour of the codebase
  ai-indexer --audio --audio-rate 150 ~/projects/my-app

  # Verbose debug output
  ai-indexer -v ~/projects/my-app

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MCP TOOLS  (available when running with --mcp)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  get_file_summary       Summary for a single file (domain, criticality, hints)
  get_dependents         List files that import a given file
  search_symbol          Find files that define or export a symbol name
  list_hotspots          Top N files by priority score
  list_orphans           Files with no importers and not an entrypoint
  list_by_blast_radius   Files sorted by 2-hop blast radius (change impact)
  list_refactor_candidates  Files with high refactor effort score

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""


class _Formatter(argparse.RawTextHelpFormatter):
    """Preserves newlines in both description/epilog and per-argument help strings."""
    def __init__(self, prog: str) -> None:
        super().__init__(prog, max_help_position=30, width=82)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ai-indexer",
        description=_DESCRIPTION,
        epilog=_EPILOG,
        formatter_class=_Formatter,
        add_help=False,  # we add our own so it appears in the right group
    )

    # ── Positional ────────────────────────────────────────────────────────────
    p.add_argument(
        "project_dir", nargs="?", default=None,
        metavar="PROJECT_DIR",
        help=(
            "Root directory of the project to analyze.\n"
            "Defaults to the current working directory.\n"
            "If the root contains a src/ folder, analysis is automatically\n"
            "restricted to that subtree."
        ),
    )

    # ── Output ────────────────────────────────────────────────────────────────
    out_group = p.add_argument_group("Output")
    out_group.add_argument(
        "--format", "-f",
        choices=["toon", "json", "md", "html", "xml", "all"],
        default="all",
        metavar="FORMAT",
        help=(
            "Output format to generate. Choices:\n"
            "  toon  — compact TOON (most token-efficient for LLMs)\n"
            "  json  — full JSON with all metadata\n"
            "  md    — Markdown summary with hotspot table\n"
            "  html  — interactive 3-D nebula dashboard\n"
            "  xml   — structured XML (recommended for Claude/Anthropic)\n"
            "  all   — generate every format above  [default]\n"
        ),
    )
    out_group.add_argument(
        "--output", "-o",
        default=None, metavar="FILE",
        help=(
            "Override the output file path.\n"
            "Only valid when a single --format is specified.\n"
            "Example: --format toon --output context.toon"
        ),
    )

    # ── Content ────────────────────────────────────────────────────────────────
    content_group = p.add_argument_group("Content enrichment")
    content_group.add_argument(
        "--instruction-file",
        default=None, metavar="FILE",
        help=(
            "Path to a plain-text (or Markdown) file whose content is injected\n"
            "as an 'instruction' field in every output.\n"
            "In XML output it becomes the first <instruction> element, which\n"
            "Claude reads as a system-level context directive.\n"
            "Can also be set via 'instruction_file:' in .indexer.yaml."
        ),
    )

    # ── Analysis ──────────────────────────────────────────────────────────────
    analysis_group = p.add_argument_group("Analysis control")
    analysis_group.add_argument(
        "--no-cache",
        action="store_true",
        help=(
            "Ignore the incremental cache (.aicontext_cache_v8.json) and\n"
            "re-analyze every file from scratch.\n"
            "Useful after updating the indexer or changing config."
        ),
    )
    analysis_group.add_argument(
        "--no-security",
        action="store_true",
        help=(
            "Disable the built-in secret/credential scanner.\n"
            "By default the indexer scans every file for patterns such as\n"
            "AWS keys, GitHub tokens, Stripe keys, private key headers,\n"
            "hard-coded passwords, JWT tokens, and DB connection strings.\n"
            "Findings appear as warnings in all output formats.\n"
            "Can also be disabled via 'security.enabled: false' in .indexer.yaml."
        ),
    )
    analysis_group.add_argument(
        "--profile",
        choices=["fast", "standard", "deep", "security"],
        default="standard",
        help="Preset analysis profile that adjusts depth and token budgets.",
    )
    analysis_group.add_argument(
        "--fail-on-warning",
        action="store_true",
        help="Exit with a non-zero code if any analysis warnings are detected.",
    )
    analysis_group.add_argument(
        "--fail-on-secret",
        action="store_true",
        help="Exit with a non-zero code if secret/credential findings are detected.",
    )
    analysis_group.add_argument(
        "--summary-only",
        action="store_true",
        help="Analyze and print the final summary without writing output files.",
    )
    analysis_group.add_argument(
        "--diagnostics",
        action="store_true",
        help="Print a diagnostics JSON report after analysis.",
    )

    # ── Integration ───────────────────────────────────────────────────────────
    integration_group = p.add_argument_group("Integrations")
    integration_group.add_argument(
        "--mcp",
        action="store_true",
        help=(
            "After indexing, start a JSON-RPC 2.0 MCP server on stdio.\n"
            "Exposes tools for IDE plugins and AI agents:\n"
            "  get_file_summary, get_dependents, search_symbol,\n"
            "  list_hotspots, list_orphans, list_by_blast_radius,\n"
            "  list_refactor_candidates.\n"
            "The server runs until stdin is closed (Ctrl-D / EOF)."
        ),
    )

    # ── Audio ─────────────────────────────────────────────────────────────────
    audio_group = p.add_argument_group(
        "Audio tour  (requires: pip install pyttsx3 pydub)"
    )
    audio_group.add_argument(
        "--audio",
        action="store_true",
        help=(
            "Generate a narrated audio tour of the codebase using the\n"
            "system's built-in text-to-speech engine (100%% offline).\n"
            "Output: tour_<project>.mp3 in the output directory.\n"
            "Requires pyttsx3 (TTS) and optionally pydub (MP3 encoding)."
        ),
    )
    audio_group.add_argument(
        "--audio-rate",
        type=int, default=160, metavar="WPM",
        help="Speech rate in words per minute.  Default: 160.",
    )
    audio_group.add_argument(
        "--audio-language",
        default="pt-BR",
        metavar="LANG",
        help="Preferred language/locale hint for voice selection, e.g. pt-BR or en-US.",
    )
    audio_group.add_argument(
        "--audio-voice",
        default=None,
        metavar="VOICE",
        help="Preferred voice name fragment for narration.",
    )
    audio_group.add_argument(
        "--bg-music",
        type=Path, default=None, metavar="FILE",
        help=(
            "Optional background music file (MP3 or WAV) mixed under the\n"
            "narration at reduced volume.  Requires pydub + ffmpeg."
        ),
    )

    # ── Misc ──────────────────────────────────────────────────────────────────
    misc_group = p.add_argument_group("Miscellaneous")
    misc_group.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable DEBUG-level logging to stderr.",
    )
    misc_group.add_argument(
        "--version",
        action="version", version=f"%(prog)s {__version__}",
        help="Show version and exit.",
    )
    misc_group.add_argument(
        "--validate-config",
        action="store_true",
        help="Validate .indexer.yaml and exit.",
    )
    misc_group.add_argument(
        "--help", "-h",
        action="help", default=argparse.SUPPRESS,
        help="Show this help message and exit.",
    )

    return p


# ── Output helpers ────────────────────────────────────────────────────────────

def _build_output(
    engine: AnalysisEngine,
    instruction: str = "",
    git_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from ai_indexer.version import __version__ as package_version
    files = engine.files
    hotspots = sorted(
        (
            HotspotRecord(
                file=f.file,
                priority_score=f.priority_score,
                pagerank=f.pagerank,
                fan_in=f.fan_in,
                refactor_effort=f.refactor_effort,
                blast_radius=f.blast_radius,
                domain=f.domain.value,
                criticality=f.criticality,
                score_explanation=f.priority_breakdown,
            )
            for f in files.values()
        ),
        key=lambda item: item.priority_score,
        reverse=True,
    )[:15]
    analysis = ProjectAnalysis(
        version=package_version,
        project=engine.root.name,
        generated_at=datetime.now(timezone.utc).isoformat(),
        stats=ProjectStats(
            total_files=len(files),
            critical_files=sum(1 for f in files.values() if f.criticality == "critical"),
            entrypoints=sum(1 for f in files.values() if f.entrypoint),
            domains=len({f.domain.value for f in files.values()}),
        ),
        files=files,
        dependency_graph=engine.graph,
        reverse_graph={k: list(v) for k, v in engine.rev.items()},
        pagerank={path: fd.pagerank for path, fd in files.items()},
        execution_flows=[],
        modules=_detect_modules(engine),
        hotspots=hotspots,
        instruction=instruction,
        git_context=git_context,
        diagnostics=_build_diagnostics(engine, git_context),
    )
    return analysis.to_dict()


def _detect_modules(engine: AnalysisEngine) -> dict[str, list[str]]:
    from pathlib import Path as _Path
    modules: dict[str, list[str]] = defaultdict(list)
    for fd in engine.files.values():
        rel = _Path(fd.file)
        key = (f"{rel.parts[0]}/{fd.domain.value}" if len(rel.parts) >= 2 else fd.domain.value)
        modules[key].append(fd.file)
    return dict(sorted(modules.items()))


def _write_outputs(
    engine: AnalysisEngine,
    output_data: dict[str, Any],
    fmt: str,
    override_path: Path | None,
    out_dir: Path,
) -> list[tuple[str, Path]]:
    """Write all requested output formats. Returns list of (format, path) tuples."""
    written: list[tuple[str, Path]] = []

    if fmt in ("toon", "all"):
        path = override_path or (out_dir / "estrutura_projeto.toon")
        validate_output_payload(output_data, "toon")
        ToonExporter().export(output_data, path)
        log.info("TOON written: %s", path)
        written.append(("toon", path))

    if fmt in ("json", "all"):
        path = override_path or (out_dir / "estrutura_projeto.json")
        validate_output_payload(output_data, "json")
        path.write_text(json.dumps(output_data, separators=(",",":"), ensure_ascii=False), encoding="utf-8")
        log.info("JSON written: %s", path)
        written.append(("json", path))

    if fmt in ("html", "all"):
        path = override_path or (out_dir / "estrutura_projeto.html")
        validate_output_payload(output_data, "html")
        HtmlExporter().export(output_data, path)
        log.info("HTML written: %s", path)
        written.append(("html", path))

    if fmt in ("md", "all"):
        path = override_path or (out_dir / "estrutura_projeto.md")
        validate_output_payload(output_data, "json")
        _write_md(engine, output_data, path)
        log.info("Markdown written: %s", path)
        written.append(("md", path))

    if fmt in ("xml", "all"):
        path = override_path or (out_dir / "estrutura_projeto.xml")
        validate_output_payload(output_data, "xml")
        XmlExporter().export(output_data, path)
        written.append(("xml", path))

    return written


def _write_md(engine: AnalysisEngine, data: dict[str, Any], path: Path) -> None:
    ver  = data.get("version","8.0.0")
    proj = data.get("project","")
    ts   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    files = engine.files
    lines = [
        f"# AI Context Index v{ver} — `{proj}`",
        f"> Generated: `{ts}`", "",
        "## System Overview",
        f"- **Total files:** {len(files)}",
        f"- **Critical:** {sum(1 for f in files.values() if f.criticality=='critical')}",
        f"- **Domains:** {len({f.domain.value for f in files.values()})}",
        f"- **Entrypoints:** {sum(1 for f in files.values() if f.entrypoint)}",
        "",
        "## Top Hotspots",
        "| File | Priority | Refactor Effort | Blast Radius | Domain | Score Signals |",
        "|------|----------|-----------------|--------------|--------|---------------|",
    ]
    for fd in sorted(files.values(), key=lambda x: x.priority_score, reverse=True)[:10]:
        top_signals = ", ".join(
            f"{name}:{value:.1f}"
            for name, value in sorted(
                fd.priority_breakdown.items(),
                key=lambda item: abs(item[1]),
                reverse=True,
            )[:3]
        )
        lines.append(
            f"| `{fd.file}` | {fd.priority_score} | {fd.refactor_effort:.1f} | "
            f"{fd.blast_radius} | {fd.domain.value} | {top_signals or '-'} |"
        )
    lines += ["", "## Architectural Warnings"]
    warns = [(fd.file, fd.warnings) for fd in files.values() if fd.warnings]
    if warns:
        for file, wl in warns[:20]:
            lines.append(f"### `{file}`")
            for w in wl[:3]:
                lines.append(f"- {w}")
            file_meta = files[file]
            classification = file_meta.hints.get("classification", {})
            domain_evidence = classification.get("domain_evidence", {})
            if domain_evidence:
                evidence = ", ".join(f"{name}:{value:.1f}" for name, value in list(domain_evidence.items())[:3])
                lines.append(f"- Domain evidence: {evidence}")
    else:
        lines.append("No warnings detected.")
    lines.append(f"\n---\n_AI Context Indexer v{ver}_{ts}_")
    path.write_text("\n".join(lines), encoding="utf-8")


def _apply_profile(config: Any, profile: str) -> Any:
    data = dict(getattr(config, "_d", {}))
    if profile == "fast":
        data["max_depth"] = min(int(data.get("max_depth", 8)), 4)
        data["chunk_max_tokens"] = min(int(data.get("chunk_max_tokens", 800)), 400)
        data["max_workers"] = min(int(data.get("max_workers", 0) or 0) or 4, 8)
    elif profile == "deep":
        data["max_depth"] = max(int(data.get("max_depth", 8)), 12)
        data["chunk_max_tokens"] = max(int(data.get("chunk_max_tokens", 800)), 1200)
        data["max_workers"] = int(data.get("max_workers", 0) or 0)
    elif profile == "security":
        data.setdefault("security", {})
        data["security"]["enabled"] = True
        data["max_depth"] = int(data.get("max_depth", 8))
    return type(config)(data)


def _build_diagnostics(
    engine: AnalysisEngine,
    git_context: dict[str, Any] | None,
) -> dict[str, Any]:
    security_enabled = engine.config.security_enabled
    secrets = sum(
        1 for fd in engine.files.values()
        for w in fd.warnings
        if "secret" in w.lower() or "credential" in w.lower() or "hardcoded" in w.lower()
    )
    return {
        "analysis_mode": "full",
        "optional_dependencies": _optional_dependency_status(),
        "git_context_enabled": bool(git_context),
        "security_scan_enabled": security_enabled,
        "secret_findings": secrets,
        "warning_count": sum(len(fd.warnings) for fd in engine.files.values()),
    }


def _optional_dependency_status() -> dict[str, bool]:
    checks = {
        "pyyaml": "yaml",
        "jinja2": "jinja2",
        "pathspec": "pathspec",
        "tiktoken": "tiktoken",
        "pyttsx3": "pyttsx3",
        "pydub": "pydub",
    }
    status: dict[str, bool] = {}
    for label, module_name in checks.items():
        try:
            __import__(module_name)
            status[label] = True
        except ImportError:
            status[label] = False
    return status


def _missing_dependency_help(feature: str) -> str:
    feature_map = {
        "audio": "Install the 'full' extra plus audio dependencies: pip install ai-indexer[full] pyttsx3 pydub",
        "html": "Install the 'full' extra to enable Jinja2 templates: pip install ai-indexer[full]",
        "config": "Install the 'full' extra to enable YAML config parsing: pip install ai-indexer[full]",
    }
    return feature_map.get(feature, "Install ai-indexer[full] for optional integrations.")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = _build_parser()
    args   = parser.parse_args()

    # ── Terminal UI ───────────────────────────────────────────────────────────
    ui = AnalysisUI(verbose=args.verbose)

    # JSON structured logging is for machine consumption (--verbose / CI pipes).
    # In normal interactive use the UI handles all output, so suppress it.
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        log.setLevel(logging.DEBUG)
    else:
        logging.getLogger().setLevel(logging.WARNING)

    root = Path(args.project_dir).resolve() if args.project_dir else Path.cwd()
    if not root.is_dir():
        ui.error(f"Not a directory: {root}")
        sys.exit(1)

    if args.validate_config:
        ok, msg = validate_config(root)
        print(msg, file=sys.stderr if not ok else sys.stdout)
        sys.exit(0 if ok else 1)

    config = load_config(root)
    if args.profile != "standard":
        config = _apply_profile(config, args.profile)
    out_dir = (root / config.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    ui.header(__version__, root)

    engine = AnalysisEngine(root, config)
    if args.no_cache:
        engine.cache.clear()

    t0 = time.time()
    engine.run(on_progress=ui.on_progress)
    ui.stop_progress()
    log.info("Analysis complete in %.2fs", time.time() - t0)

    # ── Instruction file ──────────────────────────────────────────────────────
    instruction = ""
    instr_path_str = getattr(args, "instruction_file", None) or config.instruction_file
    if instr_path_str:
        instr_path = Path(instr_path_str)
        if not instr_path.is_absolute():
            instr_path = root / instr_path
        try:
            instruction = instr_path.read_text(encoding="utf-8").strip()
            log.info("Loaded instruction file: %s", instr_path)
        except Exception as e:
            log.warning("Could not read instruction file %s: %s", instr_path, e)

    # ── Git context ───────────────────────────────────────────────────────────
    git_ctx: dict[str, Any] | None = None
    if config.git_include_logs or config.git_include_diffs or config.git_sort_by_changes:
        try:
            from ai_indexer.utils.git_context import build_git_context
            git_ctx = build_git_context(
                root,
                include_logs=config.git_include_logs,
                logs_count=config.git_logs_count,
                include_diffs=config.git_include_diffs,
                sort_by_changes=config.git_sort_by_changes,
                sort_max_commits=config.git_sort_max_commits,
            ) or None
        except Exception as e:
            log.warning("Git context failed: %s", e)

    output_data = _build_output(engine, instruction=instruction, git_context=git_ctx)
    override    = Path(args.output) if args.output else None
    written = [] if args.summary_only else _write_outputs(engine, output_data, args.format, override, out_dir)
    if args.diagnostics:
        print(json.dumps(output_data.get("diagnostics", {}), ensure_ascii=False, indent=2))

    # ── Summary ───────────────────────────────────────────────────────────────
    n_security = sum(
        1 for fd in engine.files.values()
        for w in fd.warnings
        if "secret" in w.lower() or "credential" in w.lower() or "hardcoded" in w.lower()
    )
    ui.show_summary(output_data["stats"], n_security, written)

    n_warnings = sum(len(fd.warnings) for fd in engine.files.values())
    if args.fail_on_warning and n_warnings:
        ui.error(f"Failing because {n_warnings} warning(s) were detected.")
        sys.exit(2)
    if args.fail_on_secret and n_security:
        ui.error(f"Failing because {n_security} secret finding(s) were detected.")
        sys.exit(2)

    # 🎙️ Audio Tour Integration (100% Offline)
    if args.audio:
        try:
            from ai_indexer.audio_tours.narrator import LocalNarrator
            from ai_indexer.audio_tours.mixer import finalize_audio
            from ai_indexer.audio_tours.script_builder import ScriptBuilder
            from ai_indexer.tours.generator import TourGenerator

            log.info("Generating audio tour script...")
            tour_gen = TourGenerator(engine)
            tour = tour_gen.generate_overview_tour()

            builder = ScriptBuilder()
            script_text = builder.build_full_script(tour)

            log.info("Synthesizing audio (offline)...")
            narrator = LocalNarrator(rate=args.audio_rate, language=args.audio_language, voice_name=args.audio_voice)
            temp_wav = out_dir / "tour_temp.wav"
            narrator.synthesize(script_text, temp_wav)

            final_mp3 = out_dir / f"tour_{root.name.lower()}.mp3"
            finalize_audio(temp_wav, final_mp3, args.bg_music)
            
            log.info("Audio tour generated successfully: %s", final_mp3)
        except ImportError:
            log.error("Audio dependencies not found. %s", _missing_dependency_help("audio"))
        except Exception as e:
            log.error("Failed to generate audio tour: %s", e)

    if args.mcp:
        server = MCPServer(engine.files, engine.graph, dict(engine.rev), git_context=git_ctx)
        server.serve_stdio()


if __name__ == "__main__":
    main()
