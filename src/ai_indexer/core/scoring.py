"""File priority scoring helpers."""

from __future__ import annotations

from ai_indexer.core.models import FileMetadata

_CRIT_WEIGHT = {"critical": 30.0, "infra": 20.0, "config": 10.0, "supporting": 5.0}
_COMPLEXITY_WEIGHT = {"extreme": 20.0, "high": 15.0, "medium": 8.0, "low": 3.0}
_LAYER_BONUS = {"domain": 5.0, "application": 4.0, "presentation": 3.0, "infrastructure": 2.0}


def score_file(file_meta: FileMetadata) -> tuple[int, dict[str, float]]:
    breakdown: dict[str, float] = {}
    score = 0.0

    breakdown["criticality"] = _CRIT_WEIGHT.get(file_meta.criticality, 5.0)
    score += breakdown["criticality"]

    breakdown["complexity"] = _COMPLEXITY_WEIGHT.get(file_meta.complexity_label, 3.0)
    score += breakdown["complexity"]

    breakdown["entrypoint"] = 15.0 if file_meta.entrypoint else 0.0
    score += breakdown["entrypoint"]

    pagerank_component = min(20.0, file_meta.pagerank * 1000.0)
    breakdown["pagerank"] = pagerank_component
    score += pagerank_component

    fan_in_component = min(10.0, file_meta.fan_in / 2.0)
    breakdown["fan_in"] = fan_in_component
    score += fan_in_component

    fan_out_penalty = min(5.0, max(0.0, file_meta.fan_out - 15.0))
    breakdown["fan_out_penalty"] = -fan_out_penalty
    score -= fan_out_penalty

    layer_bonus = _LAYER_BONUS.get(file_meta.layer, 0.0)
    breakdown["layer_bonus"] = layer_bonus
    score += layer_bonus

    if file_meta.is_in_cycle:
        breakdown["cycle_penalty"] = -10.0
        score -= 10.0

    if file_meta.warnings:
        warning_penalty = min(8.0, float(len(file_meta.warnings)))
        breakdown["warning_penalty"] = -warning_penalty
        score -= warning_penalty

    final_score = max(0, min(100, int(round(score))))
    return final_score, breakdown


def finalize_scores(files: dict[str, FileMetadata]) -> None:
    for file_meta in files.values():
        score, breakdown = score_file(file_meta)
        file_meta.priority_score = score
        file_meta.priority_breakdown = breakdown
