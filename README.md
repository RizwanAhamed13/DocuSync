# DocuSync

A fully local document intelligence system — upload, parse, embed, tag, and semantically search documents with no cloud APIs. Everything runs on your machine.

---

## What it does

- **Upload** PDF, DOCX, TXT, MD, JSON (up to 120 MB)
- **Parse** text-native PDFs (multi-column, tables), scanned PDFs (OCR), DOCX with embedded tables
- **Tag** automatically — local zero-shot classifier + keyword extraction
- **Search** via hybrid BM25 + semantic vector search + cross-encoder reranking
- **Zero cloud** — all models run locally (GTE embeddings/reranker, BART summarizer, DeBERTa classifier, PaddleOCR)

---

## Stack

| Component | Technology |
|---|---|
| API server | FastAPI + Uvicorn |
| Document parsing | PyMuPDF (PDF), python-docx (DOCX) |
| OCR (local) | PaddleOCR PP-OCRv4 mobile + Tesseract 5 ensemble |
| OCR (Colab GPU) | PaddleOCR PP-OCRv5 server via Cloudflare tunnel |
| Embeddings | Alibaba-NLP/gte-large-en-v1.5 (sentence-transformers) |
| Vector store | ChromaDB (cosine HNSW) |
| Keyword search | SQLite FTS5 (porter stemmer) |
| Reranking | Alibaba-NLP/gte-reranker-modernbert-base |
| Summaries | facebook/bart-large-cnn |
| Classification | MoritzLaurer/DeBERTa-v3-large-mnli-fever-anli-ling-wanli |

---

## Project structure

```
.
├── main.py                  # FastAPI app and SPA fallback
├── core/                    # Runtime config and SQLite schema
├── services/                # Parsing, OCR, embeddings, indexing, search
├── routes/                  # API route modules
├── frontend/                # React source
├── static/                  # Built frontend SPA
├── uploads/                 # Uploaded documents (gitignored, created at runtime)
├── vector_store/            # ChromaDB data (gitignored, created at runtime)
├── document_metadata.db     # SQLite database (gitignored, created at runtime)
├── requirements.txt
└── .gitignore
```

---

## Benchmark dataset

The `benchmark/` folder contains the **SyllabusQA** dataset:

> Fernandez, Scarlatos, Lan. *SyllabusQA: A Course Logistics Question Answering Dataset.*
> ACL 2024. https://aclanthology.org/2024.acl-long.557/

- **63 redacted course syllabi** across 20+ subjects
- **5,078 QA pairs** (train 3018 / val 957 / test 1103)
- Question types: single factual, multi factual, single reasoning, multi reasoning, summarization, yes/no, no answer

This dataset is used to evaluate retrieval quality. If you use it, cite the original paper.

---

## Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Start the server
PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True \
  python -m uvicorn main:app --host 0.0.0.0 --port "${APP_PORT:-80}"

# 3. Open the configured host/port
```

Key runtime overrides:

```bash
export EMBEDDING_MODEL=Alibaba-NLP/gte-large-en-v1.5
export RERANKER_MODEL=Alibaba-NLP/gte-reranker-modernbert-base
export SUMMARIZER_MODEL=facebook/bart-large-cnn
export CLASSIFIER_MODEL=MoritzLaurer/DeBERTa-v3-large-mnli-fever-anli-ling-wanli
export DOCUSYNC_UPLOAD_DIR=/path/to/uploads
export DOCUSYNC_VECTOR_DIR=/path/to/vector_store
export DOCUSYNC_DB_PATH=/path/to/document_metadata.db
```

---

## Docker and CI/CD

The repository builds a production Docker image and publishes it to:

```text
ghcr.io/rizwanahamed13/docusync:latest
```

GitHub Actions:

- `CI` compiles backend modules, builds the React frontend, and validates Docker build.
- `Docker Publish` pushes branch, tag, SHA, and `latest` images to GHCR.
- `Deploy` is manual and restarts the server through `docker-compose.prod.yml`.

Required repository secrets for manual deploy:

```text
DOCUSYNC_SSH_HOST
DOCUSYNC_SSH_USER
DOCUSYNC_SSH_KEY
```

The production compose file stores runtime data outside the image under
`/opt/docusync/data` by default.

---

## OCR acceleration (optional)

For large scanned PDFs, run PP-OCRv5 server on a free Colab T4 GPU:

```bash
# 1. Open colab_ocr_service.py in Google Colab
# 2. Runtime → T4 GPU → Run
# 3. Copy the printed trycloudflare.com URL

# 4. On your local machine:
export COLAB_OCR_URL=https://xxxx.trycloudflare.com
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

Without `COLAB_OCR_URL`, the system uses local PP-OCRv4 mobile automatically.

---

## API

| Endpoint | Method | Description |
|---|---|---|
| `/upload` | POST | Upload a document, start background ingestion |
| `/documents` | GET | List all documents |
| `/documents/{id}/status` | GET | Live ingestion progress |
| `/documents/{id}/text` | GET | Full extracted text |
| `/documents/{id}/download` | GET | Download original file |
| `/documents/{id}` | DELETE | Remove from all stores |
| `/search` | POST | `{"query": "...", "limit": 5}` |
| `/tags` | GET | Tag cloud with counts |
| `/health` | GET | System status |
| `/retag` | POST | Re-run tagger on existing documents |
| `/reset` | POST | Wipe all data |
