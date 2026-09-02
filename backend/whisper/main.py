"""Servicio Whisper: API de transcripcion de audio (independiente de Otto)."""

import asyncio
import logging

from fastapi import FastAPI, File, HTTPException, UploadFile

from .transcriber import transcribe_audio

logger = logging.getLogger("whisper")

MAX_AUDIO_SIZE = 10 * 1024 * 1024  # 10MB

app = FastAPI(title="Otto - Servicio de transcripcion (faster-whisper)", version="1.0.0")


@app.post("/transcribe")
async def transcribe(file: UploadFile = File(...)):
    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="El archivo de audio está vacío.")
    if len(audio_bytes) > MAX_AUDIO_SIZE:
        raise HTTPException(
            status_code=413,
            detail="El archivo de audio supera el límite de 10MB.",
        )

    try:
        text = await asyncio.wait_for(
            asyncio.to_thread(transcribe_audio, audio_bytes),
            timeout=60.0,
        )
        return {"text": text}
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=504,
            detail="La transcripción tomó demasiado tiempo.",
        )
    except Exception:
        logger.exception("Error al transcribir audio")
        raise HTTPException(
            status_code=500,
            detail="Error al transcribir el audio.",
        )


@app.get("/health")
async def health():
    return {"ok": True, "modelo": "small", "motor": "faster-whisper"}
