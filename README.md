# Otto - Servicio Whisper

Servicio independiente de transcripcion de voz para Otto (notas de voz).

- FastAPI en el puerto **8001**
- faster-whisper (modelo `small`, idioma es)
- `POST /transcribe` (multipart, campo `file`) -> JSON con el texto
- `GET /health`

## Endpoints

### POST /transcribe

Recibe un archivo de audio (webm, mp3, wav, etc.), lo convierte a wav 16kHz mono y lo transcribe.

Respuesta:

```json
{ "text": "texto transcrito" }
```

Limites: archivo hasta 10MB, timeout 60s.

### GET /health

Responde `{"status": "ok"}` cuando el servicio esta listo.

## Docker

```bash
docker build -t otto-whisper .
docker run -p 8001:8001 otto-whisper
```

La primera vez descarga el modelo (~460MB) a `/root/.cache/huggingface`.
