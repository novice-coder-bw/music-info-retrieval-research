FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN groupadd -g 1000 workeruser && \
    useradd -u 1000 -g workeruser -s /bin/bash -m workeruser

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install CPU PyTorch first for layer caching
RUN pip install --no-cache-dir torch torchaudio --index-url https://download.pytorch.org/whl/cpu

COPY requirements-worker.txt .
RUN pip install --no-cache-dir -r requirements-worker.txt

COPY . .
RUN mkdir -p /scratch && chown -R workeruser:workeruser /app /scratch

USER workeruser

CMD ["celery", "-A", "workers.tasks", "worker", "-c", "1", "--max-tasks-per-child=5", "--loglevel=info"]
