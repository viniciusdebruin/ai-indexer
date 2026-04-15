# ai_indexer/audio_tours/script_builder.py
import re
from typing import List

class ScriptBuilder:
    """Transforma os dados do tour em um roteiro narrativo refinado."""

    def __init__(self):
        # Dicionário de limpeza para termos técnicos
        self.replacements = {
            r"__": " dunder ",
            r"\.py": " ponto pái ",
            r"\.js": " ponto jota esse ",
            r"async": " assíncrono ",
            r"await": " espera ",
            r"SaaS": " sás ",
            r"Indexer": " Indéxer ",
        }

    def _clean_text(self, text: str) -> str:
        """Aplica refinamento fonético para vozes de sistema."""
        for pattern, replacement in self.replacements.items():
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        
        # Melhora leitura de camelCase e snake_case
        text = re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', text)
        text = text.replace("_", " ")
        return text

    def build_full_script(self, tour) -> str:
        """Cria o roteiro completo com pausas e introdução."""
        parts = []
        parts.append(f"Iniciando o tour guiado pelo projeto: {self._clean_text(tour.name)}.")
        parts.append(f"{self._clean_text(tour.description)}.")
        parts.append("Vamos passar pelos pontos mais críticos do código.")
        
        # Ordena e processa as etapas
        for step in sorted(tour.steps, key=lambda s: s.order):
            parts.append(f"Etapa {step.order}: {self._clean_text(step.title)}.")
            parts.append(f"{self._clean_text(step.explanation)}.")
            if step.file_path:
                parts.append(f"Localizado no arquivo: {self._clean_text(str(step.file_path))}.")
            parts.append(" . . . ") # Pausa entre etapas

        parts.append("Fim do tour. Agora você tem uma visão geral da arquitetura.")
        return "\n".join(parts)