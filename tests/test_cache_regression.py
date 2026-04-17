from __future__ import annotations

from ai_indexer.core.cache import AnalysisCache


def test_cache_persists_and_invalidates(tmp_path) -> None:
    path = tmp_path / "sample.py"
    path.write_text("print('hello')", encoding="utf-8")

    cache = AnalysisCache(tmp_path)
    cache.set(path, {"file": "sample.py"})
    cache.save()

    reloaded = AnalysisCache(tmp_path)
    assert reloaded.get(path) == {"file": "sample.py"}

    reloaded.invalidate(path)
    assert reloaded.get(path) is None
