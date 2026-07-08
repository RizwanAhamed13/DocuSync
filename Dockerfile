FROM node:22-bookworm-slim AS frontend-build

WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM paddlepaddle/paddle:3.1.0-gpu-cuda12.6-cudnn9.5

# System dependencies: Tesseract + OpenCV
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    libgl1 \
    libglib2.0-0 \
    wget \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies (paddlepaddle-gpu already in base image)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download model stack at build time so first startup is instant
ARG EMBEDDING_MODEL=Alibaba-NLP/gte-large-en-v1.5
ARG RERANKER_MODEL=Alibaba-NLP/gte-reranker-modernbert-base
ARG SUMMARIZER_MODEL=facebook/bart-large-cnn
ARG CLASSIFIER_MODEL=MoritzLaurer/DeBERTa-v3-large-mnli-fever-anli-ling-wanli
ARG PRELOAD_MODELS=false

RUN if [ "$PRELOAD_MODELS" = "true" ]; then python -c "\
import os; \
from sentence_transformers import SentenceTransformer, CrossEncoder; \
SentenceTransformer(os.environ.get('EMBEDDING_MODEL', '${EMBEDDING_MODEL}'), trust_remote_code=True); \
CrossEncoder(os.environ.get('RERANKER_MODEL', '${RERANKER_MODEL}')); \
print('Embedding + reranker models cached.')" ; fi

RUN if [ "$PRELOAD_MODELS" = "true" ]; then python -c "\
import os; \
from transformers import pipeline; \
pipeline('summarization', model=os.environ.get('SUMMARIZER_MODEL', '${SUMMARIZER_MODEL}')); \
pipeline('zero-shot-classification', model=os.environ.get('CLASSIFIER_MODEL', '${CLASSIFIER_MODEL}')); \
print('Summarizer + classifier cached.')" ; fi

# Copy application code
COPY main.py ./
COPY core/ ./core/
COPY services/ ./services/
COPY routes/ ./routes/
COPY scripts/ ./scripts/
COPY --from=frontend-build /static ./static/

# Runtime data directories (overridden by volume mounts)
RUN mkdir -p uploads vector_store

ENV PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True
ENV PYTHONUNBUFFERED=1
ENV APP_PORT=8000
ENV EMBEDDING_MODEL=${EMBEDDING_MODEL}
ENV RERANKER_MODEL=${RERANKER_MODEL}
ENV SUMMARIZER_MODEL=${SUMMARIZER_MODEL}
ENV CLASSIFIER_MODEL=${CLASSIFIER_MODEL}
ENV USE_OLLAMA_TAGGING=false
ENV OCR_WARMUP_ON_STARTUP=true

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8000/health >/dev/null || exit 1

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
