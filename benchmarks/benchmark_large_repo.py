"""Repeatable benchmark for large synthetic repositories."""

from __future__ import annotations

import json
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from ai_indexer.core.engine import AnalysisEngine
from ai_indexer.utils.config import IndexerConfig


def create_synthetic_repo(root: Path, files: int = 800) -> None:
    src_root = root / "src" / "app"
    src_root.mkdir(parents=True, exist_ok=True)
    for index in range(files):
        dependency = f"module_{index - 1}" if index > 0 else "module_0"
        content = (
            f"from app.{dependency} import run as dep_run\n\n"
            f"def run_{index}() -> int:\n"
            f"    total = 0\n"
            f"    for i in range(10):\n"
            f"        if i % 2 == 0:\n"
            f"            total += i\n"
            f"    return total + dep_run()\n\n"
            f"def run() -> int:\n"
            f"    return run_{index}()\n"
        )
        (src_root / f"module_{index}.py").write_text(content, encoding="utf-8")
    (root / "pyproject.toml").write_text("[project]\nname='bench'\nversion='0.0.0'\n", encoding="utf-8")


def run_benchmark(files: int = 800) -> dict[str, float]:
    with TemporaryDirectory(prefix="ai_indexer_bench_") as tmp:
        root = Path(tmp)
        create_synthetic_repo(root, files=files)
        engine = AnalysisEngine(root, IndexerConfig({"max_workers": 0, "chunk_max_tokens": 600}))
        t0 = time.perf_counter()
        engine.run()
        elapsed = time.perf_counter() - t0
        throughput = files / max(elapsed, 1e-6)
        return {
            "files": float(files),
            "elapsed_seconds": elapsed,
            "files_per_second": throughput,
            "hotspots": float(len(engine.files)),
        }


if __name__ == "__main__":
    result = run_benchmark()
    print(json.dumps(result, indent=2, ensure_ascii=False))
