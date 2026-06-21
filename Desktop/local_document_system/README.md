# DocuSync

A fully local document intelligence system — upload, parse, embed, tag, and semantically search documents with no cloud APIs. Everything runs on your machine.

---

## What it does

- **Upload** PDF, DOCX, TXT, MD, JSON (up to 120 MB)
- **Parse** text-native PDFs (multi-column, tables), scanned PDFs (OCR), DOCX with embedded tables
- **Tag** automatically — 5-layer rule-based system + Ollama LLM tagging
- **Search** via hybrid BM25 + semantic vector search + cross-encoder reranking
- **Zero cloud** — all models run locally (BGE embeddings, PaddleOCR, Ollama)

---

## Stack

| Component | Technology |
|---|---|
| API server | FastAPI + Uvicorn |
| Document parsing | PyMuPDF (PDF), python-docx (DOCX) |
| OCR (local) | PaddleOCR PP-OCRv4 mobile + Tesseract 5 ensemble |
| OCR (Colab GPU) | PaddleOCR PP-OCRv5 server via Cloudflare tunnel |
| Embeddings | BAAI/bge-base-en-v1.5 (sentence-transformers) |
| Vector store | ChromaDB (cosine HNSW) |
| Keyword search | SQLite FTS5 (porter stemmer) |
| Reranking | cross-encoder/ms-marco-MiniLM-L-6-v2 |
| AI tagging | Ollama llama3 (local) with rule-based fallback |

---

## Project structure

```
.
├── main.py                  # FastAPI app, ingestion pipeline, all API endpoints
├── parser.py                # PDF/DOCX/text extraction, OCR orchestration
├── ocr.py                   # OCR pipeline: Colab → PP-OCRv4 mobile → Tesseract
├── indexer.py               # Chunking, tagging, Ollama integration
├── search.py                # Hybrid BM25 + semantic search + cross-encoder rerank
├── embeddings.py            # BGE embedding model singleton
├── colab_ocr_service.py     # Google Colab OCR service (PP-OCRv5 server on T4 GPU)
├── static/                  # Frontend SPA (HTML + JS + CSS)
├── benchmark/               # SyllabusQA dataset (ACL 2024) — see below
│   ├── syllabi/             # 63 redacted course syllabi (PDF / DOCX / TXT)
│   └── data/dataset_split/  # 5,078 QA pairs (train / val / test)
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

# 2. Install Ollama and pull a model
# https://ollama.ai
ollama pull llama3

# 3. Start the server
PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True \
  python -m uvicorn main:app --host 0.0.0.0 --port 8000

# 4. Open http://localhost:8000
```

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
