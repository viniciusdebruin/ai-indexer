"""Architecture integrity rules applied after graph and metric enrichment."""

from __future__ import annotations

from ai_indexer.core.graph import detect_cycles
from ai_indexer.core.models import FileMetadata

_NON_ORPHAN_TYPES = {"docs", "config", "asset", "template"}


def apply_architecture_rules(
    files: dict[str, FileMetadata],
    graph: dict[str, list[str]],
) -> None:
    cycles = detect_cycles(graph)
    for node in cycles:
        file_meta = files.get(node)
        if file_meta is None:
            continue
        file_meta.is_in_cycle = True
        file_meta.warnings.append("File is part of a dependency cycle")

    for file_meta in files.values():
        if (
            file_meta.fan_in == 0
            and not file_meta.entrypoint
            and file_meta.file_type.value not in _NON_ORPHAN_TYPES
        ):
            file_meta.warnings.append("Orphan file - no file imports it and it's not an entrypoint")
