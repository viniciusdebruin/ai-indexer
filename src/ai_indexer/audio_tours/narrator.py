from __future__ import annotations

from pathlib import Path
from typing import Any

import pyttsx3


class LocalNarrator:
    """Offline narrator using the system speech engine."""

    def __init__(
        self,
        rate: int = 160,
        language: str = "pt-BR",
        voice_name: str | None = None,
    ) -> None:
        self.engine = pyttsx3.init()
        self.engine.setProperty("rate", rate)
        self.engine.setProperty("volume", 1.0)
        self.language = language
        self.voice_name = voice_name

    def list_voices(self) -> list[dict[str, str]]:
        voices: list[Any] = self.engine.getProperty("voices")
        return [
            {
                "index": str(index),
                "id": str(getattr(voice, "id", "")),
                "name": str(getattr(voice, "name", "")),
            }
            for index, voice in enumerate(voices)
        ]

    def synthesize(self, text: str, output_path: Path, voice_index: int | None = None) -> Path:
        voices: list[Any] = self.engine.getProperty("voices")
        selected_index = self._select_voice(voices, voice_index)
        if selected_index is not None and 0 <= selected_index < len(voices):
            self.engine.setProperty("voice", voices[selected_index].id)

        temp_file = output_path.with_suffix(".wav")
        self.engine.save_to_file(text, str(temp_file))
        self.engine.runAndWait()
        return temp_file

    def _select_voice(self, voices: list[Any], voice_index: int | None) -> int | None:
        if voice_index is not None:
            return voice_index
        if self.voice_name:
            needle = self.voice_name.lower()
            for index, voice in enumerate(voices):
                if needle in str(getattr(voice, "name", "")).lower():
                    return index

        language_tokens = {
            self.language.lower(),
            self.language.lower().replace("-", "_"),
            self.language.split("-")[0].lower(),
        }
        for index, voice in enumerate(voices):
            voice_blob = " ".join(
                [
                    str(getattr(voice, "id", "")),
                    str(getattr(voice, "name", "")),
                    " ".join(str(item) for item in getattr(voice, "languages", []) or []),
                ]
            ).lower()
            if any(token in voice_blob for token in language_tokens):
                return index
        return 0 if voices else None
