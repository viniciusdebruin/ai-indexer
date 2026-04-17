"""Tour generator – builds a structured narration tour from AnalysisEngine output."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ai_indexer.core.engine import AnalysisEngine


@dataclass
class TourStep:
    order: int
    title: str
    explanation: str
    file_path: Path | None = None


@dataclass
class ProjectTour:
    name: str
    description: str
    steps: list[TourStep] = field(default_factory=list)


class TourGenerator:
    """Generates a ProjectTour from an AnalysisEngine instance."""

    def __init__(self, engine: "AnalysisEngine") -> None:
        self._engine = engine

    def generate_overview_tour(self) -> ProjectTour:
        files = self._engine.files
        root  = self._engine.root

        tour = ProjectTour(
            name=root.name,
            description=(
                f"Visão geral arquitetural do projeto {root.name} "
                f"com {len(files)} arquivos analisados."
            ),
        )

        order = 1

        # Step 1 – main entrypoint
        entrypoints = sorted(
            [fd for fd in files.values() if fd.entrypoint],
            key=lambda f: f.priority_score,
            reverse=True,
        )
        if entrypoints:
            ep = entrypoints[0]
            hint = f" {ep.role_hint}" if ep.role_hint else ""
            tour.steps.append(TourStep(
                order=order,
                title="Ponto de Entrada Principal",
                explanation=(
                    f"O arquivo {ep.file} é o ponto de entrada da aplicação.{hint}"
                ),
                file_path=Path(ep.file),
            ))
            order += 1

        # Steps 2-6 – top hotspots (excluding the entrypoint already added)
        seen = {ep.file for ep in entrypoints[:1]}
        hotspots = sorted(files.values(), key=lambda f: f.priority_score, reverse=True)
        for fd in hotspots:
            if order > 6:
                break
            if fd.file in seen:
                continue
            seen.add(fd.file)
            domain_str = fd.domain.value
            tour.steps.append(TourStep(
                order=order,
                title=f"Arquivo Crítico: {Path(fd.file).name}",
                explanation=(
                    f"Prioridade {fd.priority_score}, criticidade '{fd.criticality}', "
                    f"{fd.fan_in} dependente(s). "
                    f"Domínio: {domain_str}."
                ),
                file_path=Path(fd.file),
            ))
            order += 1

        # Final step – architecture summary
        domains: set[str] = set()
        for fd in files.values():
            if fd.domain.value:
                domains.add(fd.domain.value)

        tour.steps.append(TourStep(
            order=order,
            title="Resumo Arquitetural",
            explanation=(
                f"O projeto possui {len(files)} arquivos distribuídos em "
                f"{len(domains)} domínio(s): {', '.join(sorted(str(d) for d in domains))}."
            ),
        ))

        return tour
