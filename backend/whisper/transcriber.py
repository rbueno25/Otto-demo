"""Servicio de transcripcion de notas de voz (faster-whisper).

Servicio independiente del backend de Otto: recibe un archivo de audio y
devuelve el texto transcrito. Corre en su propio contenedor para no
competir por CPU/RAM con el chat.
"""

import io
import logging
import subprocess

from faster_whisper import WhisperModel

logger = logging.getLogger(__name__)

# Model singleton loaded once (queda caliente en background)
_model: WhisperModel | None = None


def get_model() -> WhisperModel:
    """Retorna la instancia singleton de WhisperModel ("small", device="cpu", compute_type="int8")."""
    global _model
    if _model is None:
        logger.info("Cargando modelo faster-whisper (small, cpu, int8)...")
        _model = WhisperModel("small", device="cpu", compute_type="int8")
    return _model


def convert_to_wav(audio_bytes: bytes) -> bytes:
    """Convierte cualquier formato de audio de entrada a WAV 16kHz mono mediante ffmpeg."""
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        "pipe:0",
        "-ar",
        "16000",
        "-ac",
        "1",
        "-f",
        "wav",
        "pipe:1",
    ]
    process = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdout, stderr = process.communicate(input=audio_bytes, timeout=30)
    if process.returncode != 0:
        error_msg = stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"Error al convertir audio con ffmpeg: {error_msg}")
    return stdout


def transcribe_audio(audio_bytes: bytes) -> str:
    """Convierte los bytes de audio a WAV y transcribe el contenido usando faster-whisper en espanol."""
    model = get_model()
    wav_bytes = convert_to_wav(audio_bytes)
    segments, _ = model.transcribe(io.BytesIO(wav_bytes), language="es", beam_size=1)
    text = " ".join(seg.text.strip() for seg in segments if seg.text.strip()).strip()
    return text
