"""Narrative context generation for file summaries."""

from __future__ import annotations

from ai_indexer.core.models import FileMetadata


def build_contexts(files: dict[str, FileMetadata]) -> None:
    for file_meta in files.values():
        if file_meta.module_doc:
            file_meta.role_hint = f"{file_meta.file_type.value} - {file_meta.module_doc.strip()[:80]}"
        else:
            file_meta.role_hint = f"{file_meta.file_type.value} for {file_meta.domain.value}"

        capabilities = []
        funcs = file_meta.capabilities.get("functions")
        if funcs:
            capabilities.append(f"functions: {', '.join(funcs[:3])}")
        classes = file_meta.capabilities.get("classes")
        if classes:
            capabilities.append(f"classes: {', '.join(classes[:2])}")

        cap_str = f" [{'; '.join(capabilities)}]" if capabilities else ""
        warn_str = f" [{len(file_meta.warnings)} warnings]" if file_meta.warnings else ""
        file_meta.context = (
            f"{file_meta.criticality.title()} {file_meta.file_type.value} for '{file_meta.domain.value}' domain."
            f"{cap_str}{warn_str} "
            f"Priority: {file_meta.priority_score}/100. "
            f"Blast radius: {file_meta.blast_radius} files. "
            f"Refactor effort: {file_meta.refactor_effort:.1f}."
        )
