# ai_indexer/audio_tours/narrator.py
import pyttsx3
from pathlib import Path
from typing import Optional

class LocalNarrator:
    """Narrador 100% offline utilizando motores nativos do SO."""

    def __init__(self, rate: int = 160):
        self.engine = pyttsx3.init()
        self.engine.setProperty('rate', rate)  # Velocidade da fala
        self.engine.setProperty('volume', 1.0)

    def list_voices(self):
        """Lista vozes disponíveis no sistema para o usuário escolher."""
        voices = self.engine.getProperty('voices')
        for index, voice in enumerate(voices):
            print(f"{index}: {voice.name} [{voice.languages}]")

    def synthesize(self, text: str, output_path: Path, voice_index: Optional[int] = None) -> Path:
        """
        Converte texto para áudio. 
        Nota: pyttsx3 gera arquivos .wav ou .aiff nativamente dependendo do SO.
        """
        voices = self.engine.getProperty('voices')
        
        # Tenta selecionar uma voz em português se disponível e não especificada
        if voice_index is None:
            for i, v in enumerate(voices):
                if 'PT' in v.id.upper() or 'brazil' in v.name.lower():
                    voice_index = i
                    break
        
        if voice_index is not None:
            self.engine.setProperty('voice', voices[voice_index].id)

        # pyttsx3 salva em formato nativo (geralmente WAV)
        temp_file = output_path.with_suffix('.wav')
        self.engine.save_to_file(text, str(temp_file))
        self.engine.runAndWait()
        
        return temp_file