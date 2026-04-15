"""CLI entrypoint for AI Context Indexer v8.0.0."""

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

from ai_indexer import __version__
from ai_indexer.core.engine import AnalysisEngine
from ai_indexer.exporters.html import HtmlExporter
from ai_indexer.exporters.toon import ToonExporter
from ai_indexer.mcp.server import MCPServer
from ai_indexer.utils.config import load_config

# ── Structured JSON logging ───────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","msg":"%(message)s"}',
    datefmt="%Y-%m-%dT%H:%M:%S",
    stream=sys.stderr,
)
log = logging.getLogger("ai-indexer")


# ── Argument parser ───────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ai-indexer",
        description=f"AI Context Indexer v{__version__} – indexes a project for LLM consumption.",
    )
    p.add_argument(
        "project_dir", nargs="?", default=None,
        help="Root directory to index (default: cwd)",
    )
    p.add_argument(
        "--format", choices=["toon","json","md","html","all"], default="all",
        help="Output format (default: all)",
    )
    p.add_argument(
        "--output", default=None, metavar="FILE",
        help="Override output file path (single-format modes only)",
    )
    p.add_argument("--verbose", "-v", action="store_true", help="DEBUG logging")
    p.add_argument("--mcp", action="store_true",
                   help="After indexing, start an MCP JSON-RPC 2.0 server on stdio")
    p.add_argument("--no-cache", action="store_true", help="Ignore analysis cache")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    # --- Audio Tour Options (100% Offline) ---
    audio_group = p.add_argument_group("Audio Tour Options")
    audio_group.add_argument(
        "--audio", action="store_true", 
        help="Generate a narrated audio tour (MP3) using local system voices."
    )
    audio_group.add_argument(
        "--audio-rate", type=int, default=160, 
        help="Speech speed rate (default: 160)."
    )
    audio_group.add_argument(
        "--bg-music", type=Path, default=None,
        help="Path to an optional background music file (MP3/WAV)."
    )
    
    return p


# ── Output helpers ────────────────────────────────────────────────────────────

def _build_output(engine: AnalysisEngine) -> dict[str, Any]:
    from ai_indexer.core.engine import VERSION
    files = engine.files
    return {
        "version":   VERSION,
        "project":   engine.root.name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "stats": {
            "total_files":   len(files),
            "critical_files": sum(1 for f in files.values() if f.criticality == "critical"),
            "entrypoints":   sum(1 for f in files.values() if f.entrypoint),
            "domains":       len({f.domain.value for f in files.values()}),
        },
        "files": {path: fd.to_dict(compact=True) for path, fd in sorted(files.items())},
        "dependency_graph": engine.graph,
        "reverse_graph":    {k: list(v) for k, v in engine.rev.items()},
        "pagerank":         {path: fd.pagerank for path, fd in files.items()},
        "execution_flows":  [],
        "modules":          _detect_modules(engine),
        "hotspots": sorted(
            [{"file": f.file, "priority_score": f.priority_score, "pagerank": f.pagerank,
              "fan_in": f.fan_in, "refactor_effort": round(f.refactor_effort, 4),
              "blast_radius": f.blast_radius}
             for f in files.values()],
            key=lambda x: x["priority_score"], reverse=True,
        )[:15],
    }


def _detect_modules(engine: AnalysisEngine) -> dict[str, list[str]]:
    from pathlib import Path as _Path
    modules: dict[str, list[str]] = defaultdict(list)
    for fd in engine.files.values():
        rel = _Path(fd.file)
        key = (f"{rel.parts[0]}/{fd.domain.value}" if len(rel.parts) >= 2 else fd.domain.value)
        modules[key].append(fd.file)
    return dict(sorted(modules.items()))


def _write_outputs(engine: AnalysisEngine, output_data: dict[str, Any],
                   fmt: str, override_path: Path | None, out_dir: Path) -> None:
    if fmt in ("toon", "all"):
        path = override_path or (out_dir / "estrutura_projeto.toon")
        ToonExporter().export(output_data, path)
        log.info("TOON written: %s", path)

    if fmt in ("json", "all"):
        path = override_path or (out_dir / "estrutura_projeto.json")
        path.write_text(json.dumps(output_data, separators=(",",":"), ensure_ascii=False), encoding="utf-8")
        log.info("JSON written: %s", path)

    if fmt in ("html", "all"):
        path = override_path or (out_dir / "estrutura_projeto.html")
        HtmlExporter().export(output_data, path)
        log.info("HTML written: %s", path)

    if fmt in ("md", "all"):
        path = override_path or (out_dir / "estrutura_projeto.md")
        _write_md(engine, output_data, path)
        log.info("Markdown written: %s", path)


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
        "| File | Priority | Refactor Effort | Blast Radius | Domain |",
        "|------|----------|-----------------|--------------|--------|",
    ]
    for fd in sorted(files.values(), key=lambda x: x.priority_score, reverse=True)[:10]:
        lines.append(
            f"| `{fd.file}` | {fd.priority_score} | {fd.refactor_effort:.1f} | "
            f"{fd.blast_radius} | {fd.domain.value} |"
        )
    lines += ["", "## Architectural Warnings"]
    warns = [(fd.file, fd.warnings) for fd in files.values() if fd.warnings]
    if warns:
        for file, wl in warns[:20]:
            lines.append(f"### `{file}`")
            for w in wl[:3]:
                lines.append(f"- {w}")
    else:
        lines.append("No warnings detected.")
    lines.append(f"\n---\n_AI Context Indexer v{ver}_{ts}_")
    path.write_text("\n".join(lines), encoding="utf-8")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = _build_parser()
    args   = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        log.setLevel(logging.DEBUG)

    root = Path(args.project_dir).resolve() if args.project_dir else Path.cwd()
    if not root.is_dir():
        log.error("Not a directory: %s", root)
        sys.exit(1)

    config = load_config(root)
    out_dir = (root / config.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    engine = AnalysisEngine(root, config)
    if args.no_cache:
        engine.cache.clear()

    t0 = time.time()
    engine.run()
    log.info("Analysis complete in %.2fs", time.time() - t0)

    output_data = _build_output(engine)
    override    = Path(args.output) if args.output else None
    _write_outputs(engine, output_data, args.format, override, out_dir)

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
            narrator = LocalNarrator(rate=args.audio_rate)
            temp_wav = out_dir / "tour_temp.wav"
            narrator.synthesize(script_text, temp_wav)

            final_mp3 = out_dir / f"tour_{root.name.lower()}.mp3"
            finalize_audio(temp_wav, final_mp3, args.bg_music)
            
            log.info("Audio tour generated successfully: %s", final_mp3)
        except ImportError:
            log.error("Audio dependencies not found. Install with: pip install pyttsx3 pydub")
        except Exception as e:
            log.error("Failed to generate audio tour: %s", e)

    if args.mcp:
        server = MCPServer(engine.files, engine.graph, dict(engine.rev))
        server.serve_stdio()


if __name__ == "__main__":
    main()