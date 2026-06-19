FROM pytorch/pytorch:2.3.0-cuda12.1-cudnn8-runtime

# System dependencies: Tesseract + OpenCV + curl
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    wget \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download BGE-M3 + bge-reranker-large at build time (no cold-start delay)
RUN python -c "\
from sentence_transformers import SentenceTransformer, CrossEncoder; \
SentenceTransformer('BAAI/bge-m3'); \
CrossEncoder('BAAI/bge-reranker-large'); \
print('Models cached.')"

# Copy application code
COPY main.py parser.py ocr.py indexer.py search.py embeddings.py ./
COPY static/ ./static/

# Runtime data directories (overridden by volume mounts)
RUN mkdir -p uploads vector_store

ENV PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True
ENV PYTHONUNBUFFERED=1
ENV EMBEDDING_MODEL=BAAI/bge-m3
ENV EMBEDDING_DEVICE=cuda
ENV EMBEDDING_BATCH_SIZE=32

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
