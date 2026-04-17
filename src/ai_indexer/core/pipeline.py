"""Named analysis stages for the project indexer."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from ai_indexer.core.discovery import build_file_index, collect_files
from ai_indexer.utils.io import build_import_resolution_state

log = logging.getLogger("ai-indexer.pipeline")


@dataclass(slots=True)
class AnalysisPipeline:
    engine: Any

    def run(self, on_progress: Callable[[int, int], None] | None = None) -> None:
        context = self._discover(on_progress)
        self._index(context)
        self._analyse(context, on_progress)
        self._finalize()

    def _discover(self, on_progress: Callable[[int, int], None] | None) -> dict[str, Any]:
        log.info("Stage: discover")
        paths = collect_files(
            self.engine.root,
            self.engine.config,
            self.engine.ignore_dirs,
            self.engine.ignore_patterns,
            self.engine.generated_files,
            self.engine.text_suffixes,
            self.engine.special_text_filenames,
        )
        if on_progress:
            on_progress(0, len(paths))
        return {"paths": paths}

    def _index(self, context: dict[str, Any]) -> None:
        log.info("Stage: index")
        paths = context["paths"]
        self.engine._file_index = build_file_index(self.engine.root, paths)
        context["aliases"], context["bare"] = build_import_resolution_state(
            self.engine.root,
            self.engine._file_index,
        )

    def _analyse(
        self,
        context: dict[str, Any],
        on_progress: Callable[[int, int], None] | None,
    ) -> None:
        log.info("Stage: analyse")
        results = self.engine._analyse_parallel(
            context["paths"],
            context["aliases"],
            context["bare"],
            self.engine.config.max_workers,
            on_progress,
        )
        self.engine._update_files_and_cache(results)

    def _finalize(self) -> None:
        log.info("Stage: finalize")
        self.engine._post_process()
