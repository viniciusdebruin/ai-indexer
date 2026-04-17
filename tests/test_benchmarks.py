from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_benchmark_module():
    benchmark_path = Path(__file__).resolve().parents[1] / "benchmarks" / "benchmark_large_repo.py"
    spec = importlib.util.spec_from_file_location("benchmark_large_repo", benchmark_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_large_repo_benchmark_threshold() -> None:
    benchmark_module = _load_benchmark_module()
    result = benchmark_module.run_benchmark(files=300)
    assert result["elapsed_seconds"] < 25.0
    assert result["files_per_second"] > 5.0
