# Contexto de build: backend/whisper/ (Base Directory en Coolify)
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /app

# ffmpeg estatico: binario unico, evita apt-get con ~204 dependencias
# (build mucho mas ligero: menos RAM/disco en el servidor)
COPY --from=mwader/static-ffmpeg:7.1.1 /ffmpeg /usr/local/bin/ffmpeg

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY __init__.py transcriber.py main.py ./whisper/

EXPOSE 8001
CMD ["uvicorn", "whisper.main:app", "--host", "0.0.0.0", "--port", "8001"]
