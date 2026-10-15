# --- Stage 1: build the web UI -------------------------------------------------
FROM node:22-slim AS ui
WORKDIR /ui
COPY ui/package.json ui/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY ui/ ./
RUN npm run build

# --- Stage 2: API (+ the built UI, served by FastAPI at /) ---------------------
FROM python:3.12-slim

WORKDIR /srv
# git: lets /ingest clone a public repository from a URL.
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download the embedding + reranker models so the first request is fast.
# Non-fatal: if the build is offline they download on first use instead.
ENV FASTEMBED_CACHE_PATH=/models
RUN python -c "from fastembed import TextEmbedding; from fastembed.rerank.cross_encoder import TextCrossEncoder; TextEmbedding('BAAI/bge-small-en-v1.5'); TextCrossEncoder('Xenova/ms-marco-MiniLM-L-6-v2')" \
    || echo "model prefetch skipped"

COPY app ./app
COPY evals ./evals
COPY --from=ui /ui/dist ./ui/dist
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
