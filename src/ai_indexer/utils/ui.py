"""Terminal UI for ai-indexer.

Uses `rich` for a live progress bar and structured summary when:
  - stderr is a TTY
  - rich is installed
  - --verbose flag is NOT set

Falls back to clean plain-text output otherwise (CI, pipes, etc.).
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

_RICH = False
try:
    import rich  # noqa: F401
    _RICH = True
except ImportError:
    pass


def _file_size(path: Path) -> str:
    try:
        b = path.stat().st_size
        if b < 1024:
            return f"{b} B"
        if b < 1024 * 1024:
            return f"{b / 1024:.0f} KB"
        return f"{b / 1024 / 1024:.1f} MB"
    except OSError:
        return ""


class AnalysisUI:
    """
    Coordinates all terminal output for one indexing run.

    Pass `ui.on_progress` as the `on_progress` kwarg to `engine.run()`.
    After the engine finishes call `ui.stop_progress()` then
    `ui.show_summary(stats, n_security_warnings, output_paths)`.
    """

    def __init__(self, verbose: bool = False) -> None:
        self._verbose = verbose
        self._use_rich = _RICH and not verbose and sys.stderr.isatty()
        self._t0: float = 0.0
        self._total: int = 0
        self._progress: Any = None   # rich Progress instance
        self._task_id: Any = None
        self._console: Any = None

        if self._use_rich:
            from rich.console import Console
            self._console = Console(stderr=True, highlight=False)

    @property
    def active(self) -> bool:
        """True when rich UI is running (logging should be suppressed)."""
        return self._use_rich

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def header(self, version: str, root: Path) -> None:
        """Print the top banner. Call once before engine.run()."""
        self._t0 = time.time()
        if self._use_rich:
            self._console.print()
            self._console.print(f"  [bold]AI Context Indexer[/]  [dim]v{version}[/]")
            self._console.print(f"  [dim]{root}[/]")
            self._console.print()

    def on_progress(self, done: int, total: int) -> None:
        """
        Callback for engine.run().

        Called with (0, N) once the file scan is complete (N = file count),
        then with (1, N), (2, N) ... (N, N) as each file is analysed.
        """
        if not self._use_rich:
            return

        if done == 0:
            # File count just became known — start the live progress bar
            self._total = total
            from rich.progress import (
                BarColumn,
                MofNCompleteColumn,
                Progress,
                SpinnerColumn,
                TextColumn,
                TimeElapsedColumn,
            )
            self._progress = Progress(
                SpinnerColumn(),
                TextColumn("  [bold cyan]Analyzing[/]"),
                BarColumn(bar_width=40),
                MofNCompleteColumn(),
                TextColumn("[dim]files[/]"),
                TimeElapsedColumn(),
                console=self._console,
                transient=False,
            )
            self._progress.start()
            self._task_id = self._progress.add_task("", total=total)
        else:
            if self._progress is not None and self._task_id is not None:
                self._progress.update(self._task_id, completed=done)

    def stop_progress(self) -> None:
        """Mark progress complete and stop the live display."""
        if self._use_rich and self._progress is not None:
            self._progress.update(self._task_id, completed=self._total)
            self._progress.stop()
            self._progress = None

    def show_summary(
        self,
        stats: dict[str, Any],
        security_warnings: int,
        outputs: list[tuple[str, Path]],
    ) -> None:
        """Print the final summary. Call after all output files are written."""
        elapsed = time.time() - self._t0
        if self._use_rich:
            self._rich_summary(stats, security_warnings, outputs, elapsed)
        else:
            self._plain_summary(stats, security_warnings, outputs, elapsed)

    def error(self, msg: str) -> None:
        if self._use_rich:
            self._console.print(f"\n  [bold red]✖[/]  {msg}\n")
        else:
            print(f"Error: {msg}", file=sys.stderr)

    # ── Rendering ─────────────────────────────────────────────────────────────

    def _rich_summary(
        self,
        stats: dict[str, Any],
        security_warnings: int,
        outputs: list[tuple[str, Path]],
        elapsed: float,
    ) -> None:
        c = self._console
        c.print()

        # Stats row
        c.print(
            f"  [bold]{stats.get('total_files', 0)}[/] files"
            f"  [dim]·[/]  "
            f"[bold red]{stats.get('critical_files', 0)}[/] critical"
            f"  [dim]·[/]  "
            f"[bold blue]{stats.get('domains', 0)}[/] domains"
            f"  [dim]·[/]  "
            f"[bold green]{stats.get('entrypoints', 0)}[/] entrypoints"
        )

        if security_warnings:
            c.print()
            c.print(
                f"  [bold yellow]⚠[/]  "
                f"[yellow]{security_warnings} potential secret(s) detected[/]"
                f"  [dim]— review warnings in output files[/]"
            )

        c.print()

        # Output files
        for _fmt, path in outputs:
            size = _file_size(path)
            c.print(f"  [green]✔[/]  [cyan]{path.name:<40}[/]  [dim]{size}[/]")

        c.print()
        c.print(f"  [dim]Done in {elapsed:.2f}s[/]")
        c.print()

    def _plain_summary(
        self,
        stats: dict[str, Any],
        security_warnings: int,
        outputs: list[tuple[str, Path]],
        elapsed: float,
    ) -> None:
        print(
            f"\nFiles: {stats.get('total_files', 0)}"
            f"  Critical: {stats.get('critical_files', 0)}"
            f"  Domains: {stats.get('domains', 0)}"
            f"  Entrypoints: {stats.get('entrypoints', 0)}",
            file=sys.stderr,
        )
        if security_warnings:
            print(f"⚠  {security_warnings} potential secret(s) detected", file=sys.stderr)
        print("", file=sys.stderr)
        for _fmt, path in outputs:
            size = _file_size(path)
            print(f"  ✔  {path.name}  {size}", file=sys.stderr)
        print(f"\nDone in {elapsed:.2f}s", file=sys.stderr)
