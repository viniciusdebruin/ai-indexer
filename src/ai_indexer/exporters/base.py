"""Abstract base exporter."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class BaseExporter(ABC):
    """All output format exporters implement this interface."""

    #: File extension produced by this exporter (with leading dot)
    extension: str = ""

    @abstractmethod
    def export(self, data: dict[str, Any], output_path: Path) -> None:
        """Serialize *data* and write to *output_path*."""
        ...
