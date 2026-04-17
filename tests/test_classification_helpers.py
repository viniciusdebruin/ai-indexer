from __future__ import annotations

from pathlib import Path

from ai_indexer.core.classification import (
    complexity,
    detect_domain,
    detect_layer,
    detect_type,
    extract_hints,
    get_criticality,
    is_entrypoint,
)
from ai_indexer.core.models import ConfidenceValue
from ai_indexer.utils.config import IndexerConfig


def test_detect_type_prefers_segment_rules() -> None:
    result = detect_type(Path("src/services/payments.py"), "def run(): pass", IndexerConfig({}))

    assert result == ConfidenceValue("service", 0.9)


def test_detect_type_detects_entrypoint_from_main_guard() -> None:
    src = "if __name__ == '__main__':\n    main()"

    result = detect_type(Path("src/bootstrap.py"), src, IndexerConfig({}))

    assert result == ConfidenceValue("entrypoint", 0.8)
    assert is_entrypoint(Path("src/bootstrap.py"), src)


def test_detect_domain_and_layer_and_criticality() -> None:
    config = IndexerConfig(
        {
            "domain_overrides": {"src/legacy/": "backend"},
            "criticality_overrides": {"src/legacy/": "infra"},
        }
    )

    domain, secondary = detect_domain(Path("src/billing/invoice.py"), "", config)

    assert domain == ConfidenceValue("billing", 0.95)
    assert secondary is None
    assert detect_layer("config", Path("src/settings.json"), "") == "infrastructure"
    assert get_criticality(Path("src/legacy/file.py"), "module", config) == "infra"


def test_complexity_and_hints() -> None:
    score, label = complexity(
        220,
        ["load_data", "process_data"],
        ["Service"],
        ["dep1", "dep2"],
        "line1\nline2\nline3\nSELECT * FROM users\n",
    )
    hints = extract_hints(
        Path("src/billing/invoice_service.py"),
        "SELECT * FROM invoices WHERE id = 1",
        "service",
        "billing",
        ["load_data", "process_data"],
        ["InvoiceService"],
        ["requests", "@app/core"],
        "Invoice service.\nMore text.",
    )

    assert score > 0
    assert label in {"low", "medium", "high", "extreme"}
    assert hints["description"] == "Invoice service."
    assert "billing" in hints["keywords"]
    assert "invoiceservice" not in hints["keywords"]
