# Contexto de build: backend/whisper/ (Base Directory en Coolify)
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY __init__.py transcriber.py main.py ./whisper/

EXPOSE 8001

CMD ["uvicorn", "whisper.main:app", "--host", "0.0.0.0", "--port", "8001"]
