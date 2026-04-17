"""XML output exporter.

Produces a structured XML document suitable for direct LLM consumption.
Anthropic recommends XML format for Claude — tags make document structure
unambiguous and easy to parse.

Schema outline:
  <ai_index version="..." project="..." generated_at="...">
    <instruction>...</instruction>           (if set)
    <file_summary total_files="..." critical="..." domains="..." entrypoints="..."/>
    <hotspots>
      <file path="..." priority="..." criticality="..." domain="..." .../>
    </hotspots>
    <files>
      <file path="..." criticality="..." domain="..." entrypoint="..." ...>
        <module_doc>...</module_doc>
        <functions>...</functions>
        <dependencies>...</dependencies>
        <warnings>...</warnings>
      </file>
    </files>
    <git_context>
      <recent_commits>...</recent_commits>
      <diff_stat>...</diff_stat>
      <change_frequency>...</change_frequency>
    </git_context>
  </ai_index>
"""

from __future__ import annotations

import logging
from pathlib import Path
from collections.abc import Mapping
from typing import Any
from xml.etree import ElementTree as ET

from ai_indexer.exporters.base import BaseExporter
from ai_indexer.core.output import normalize_file_payload

log = logging.getLogger("ai-indexer.xml")


def _sub(
    parent: ET.Element,
    tag: str,
    text: str | None = None,
    attrib: Mapping[str, str] | None = None,
    **extra: str,
) -> ET.Element:
    attrs: dict[str, str] = dict(attrib or {})
    attrs.update(extra)
    el = ET.SubElement(parent, tag, attrs)
    if text is not None:
        el.text = text
    return el


class XmlExporter(BaseExporter):
    extension = ".xml"

    def export(self, data: dict[str, Any], output_path: Path) -> None:
        root_el = ET.Element(
            "ai_index",
            version=str(data.get("version", "")),
            project=str(data.get("project", "")),
            generated_at=str(data.get("generated_at", "")),
        )

        # ── Instruction ──────────────────────────────────────────────────────
        instruction = data.get("instruction", "")
        if instruction:
            _sub(root_el, "instruction", instruction)

        # ── File summary ─────────────────────────────────────────────────────
        stats = data.get("stats", {})
        ET.SubElement(
            root_el, "file_summary",
            total_files=str(stats.get("total_files", 0)),
            critical=str(stats.get("critical_files", stats.get("critical", 0))),
            domains=str(stats.get("domains", 0)),
            entrypoints=str(stats.get("entrypoints", 0)),
        )

        # ── Hotspots ─────────────────────────────────────────────────────────
        hotspots_el = ET.SubElement(root_el, "hotspots")
        for h in data.get("hotspots", []):
            hotspot_el = ET.SubElement(
                hotspots_el, "file",
                path=str(h.get("file", "")),
                priority=str(h.get("priority_score", 0)),
                pagerank=f'{h.get("pagerank", 0):.4f}',
                fan_in=str(h.get("fan_in", 0)),
                refactor_effort=f'{h.get("refactor_effort", 0):.2f}',
                blast_radius=str(h.get("blast_radius", 0)),
            )
            explanation = h.get("score_explanation") or {}
            if explanation:
                explain_el = ET.SubElement(hotspot_el, "score_explanation")
                for key, value in sorted(explanation.items()):
                    _sub(explain_el, "signal", None, name=str(key), value=str(value))

        # ── Files ─────────────────────────────────────────────────────────────
        files_el = ET.SubElement(root_el, "files")
        for path, fd in sorted(data.get("files", {}).items()):
            normalized = normalize_file_payload(fd, path)
            domain_val = normalized["domain"]["value"]
            criticality = normalized["criticality"]
            module_doc = normalized["module_doc"] or ""
            internal = normalized["internal_dependencies"]

            file_el = ET.SubElement(
                files_el, "file",
                path=normalized["file"],
                criticality=criticality,
                domain=domain_val,
                entrypoint="true" if normalized["entrypoint"] else "false",
                priority=str(normalized["priority_score"]),
                fan_in=str(normalized["fan_in"]),
            )

            # Module doc
            if module_doc:
                _sub(file_el, "module_doc", module_doc)

            # Functions / classes / exports
            caps = normalized["capabilities"]
            funcs = caps.get("functions", [])
            classes = caps.get("classes", [])
            exports = caps.get("exports", [])
            if funcs or classes or exports:
                caps_el = ET.SubElement(file_el, "capabilities")
                if funcs:
                    _sub(caps_el, "functions", ", ".join(funcs[:20]))
                if classes:
                    _sub(caps_el, "classes", ", ".join(classes[:20]))
                if exports:
                    _sub(caps_el, "exports", ", ".join(exports[:20]))

            # Internal dependencies
            if internal:
                deps_el = ET.SubElement(file_el, "dependencies")
                for dep in internal[:20]:
                    _sub(deps_el, "dep", dep)

            # Warnings
            warns = normalized["warnings"]
            if warns:
                warns_el = ET.SubElement(file_el, "warnings")
                for w in warns[:5]:
                    _sub(warns_el, "warning", w)
            explanation = normalized["priority_breakdown"]
            if explanation:
                explain_el = ET.SubElement(file_el, "score_explanation")
                for key, value in sorted(explanation.items()):
                    _sub(explain_el, "signal", None, name=str(key), value=str(value))
            hints = normalized["hints"]
            if hints:
                hints_el = ET.SubElement(file_el, "analysis_hints")
                for key, value in sorted(hints.items()):
                    if isinstance(value, list):
                        bucket = ET.SubElement(hints_el, key)
                        for item in value[:10]:
                            _sub(bucket, "item", str(item))
                    else:
                        _sub(hints_el, key, str(value))

        # ── Git context ───────────────────────────────────────────────────────
        git_ctx = data.get("git_context")
        if git_ctx:
            git_el = ET.SubElement(root_el, "git_context")

            commits = git_ctx.get("recent_commits", [])
            if commits:
                commits_el = ET.SubElement(git_el, "recent_commits")
                for c in commits:
                    ET.SubElement(
                        commits_el, "commit",
                        hash=c.get("hash", ""),
                        author=c.get("author", ""),
                        date=c.get("date", ""),
                        message=c.get("message", ""),
                    )

            diff_stat = git_ctx.get("diff_stat", "")
            if diff_stat:
                _sub(git_el, "diff_stat", diff_stat)

            freq = git_ctx.get("change_frequency", {})
            if freq:
                freq_el = ET.SubElement(git_el, "change_frequency")
                for fp, count in sorted(freq.items(), key=lambda x: -x[1])[:30]:
                    ET.SubElement(freq_el, "file", path=fp, changes=str(count))

        diagnostics = data.get("diagnostics")
        if diagnostics:
            diag_el = ET.SubElement(root_el, "diagnostics")
            for key, value in sorted(diagnostics.items()):
                if isinstance(value, dict):
                    section = ET.SubElement(diag_el, key)
                    for inner_key, inner_value in sorted(value.items()):
                        _sub(section, "item", None, name=str(inner_key), value=str(inner_value))
                else:
                    _sub(diag_el, key, str(value))

        # ── Serialise ─────────────────────────────────────────────────────────
        ET.indent(root_el, space="  ")
        tree = ET.ElementTree(root_el)
        with output_path.open("wb") as fh:
            tree.write(fh, encoding="utf-8", xml_declaration=True)
        log.info("XML written: %s", output_path)
