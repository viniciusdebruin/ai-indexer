# ai_indexer/audio_tours/mixer.py
from pathlib import Path
from typing import Optional # Adicionado
from pydub import AudioSegment

def finalize_audio(wav_path: Path, output_path: Path, bg_music: Optional[Path] = None):
    """Converte para MP3 e opcionalmente adiciona trilha sonora local."""
    
    if not wav_path.exists():
        return

    # Carrega a narração
    narrative = AudioSegment.from_wav(str(wav_path))
    
    # Aplica um leve ganho (+3 dB) para encorpar a voz sintética
    narrative = narrative + 3
    
    if bg_music and bg_music.exists():
        bg = AudioSegment.from_file(str(bg_music))
        # Ajusta volume da música para -20dB relativo à voz
        bg = bg - 20 
        # Mixagem com loop da música
        combined = narrative.overlay(bg, loop=True)
    else:
        combined = narrative

    # Exporta como MP3
    combined.export(str(output_path), format="mp3", bitrate="128k")
    
    # Limpa temporário
    wav_path.unlink()