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
RUN python -c "\
from sentence_transformers import SentenceTransformer, CrossEncoder; \
SentenceTransformer('BAAI/bge-large-en-v1.5'); \
CrossEncoder('Alibaba-NLP/gte-reranker-modernbert-base'); \
print('Embedding + reranker models cached.')"

RUN python -c "\
from transformers import pipeline; \
pipeline('summarization', model='sshleifer/distilbart-cnn-12-6'); \
pipeline('zero-shot-classification', model='MoritzLaurer/DeBERTa-v3-large-mnli-fever-anli-ling-wanli'); \
print('DistilBART + DeBERTa cached.')"

# Copy application code
COPY main.py parser.py ocr.py indexer.py search.py embeddings.py ./
COPY static/ ./static/

# Runtime data directories (overridden by volume mounts)
RUN mkdir -p uploads vector_store

ENV PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
