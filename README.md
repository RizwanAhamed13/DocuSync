# DocuSync

DocuSync is a local document intelligence system for uploading, parsing, tagging, indexing, and searching documents without relying on cloud APIs. The main application lives in `Desktop/local_document_system`.

## What It Does

- Upload PDF, DOCX, TXT, Markdown, and JSON files
- Extract text from text-native and scanned documents
- Run OCR with PaddleOCR and Tesseract fallbacks
- Generate document summaries, metadata, and tags
- Store embeddings in ChromaDB for semantic search
- Combine keyword search, vector search, and reranking
- Serve a local web interface through FastAPI static files

## Tech Stack

| Area | Technology |
| --- | --- |
| API | FastAPI, Uvicorn |
| Frontend | React, Vite |
| Parsing | PyMuPDF, python-docx |
| OCR | PaddleOCR, Tesseract |
| Search | SQLite FTS, ChromaDB, sentence-transformers |
| AI Metadata | Ollama with rule-based fallback |
| Deployment | Docker, Docker Compose |

## Project Structure

```text
DocuSync/
└── Desktop/
    └── local_document_system/
        ├── main.py                 # FastAPI app and API routes
        ├── parser.py               # Document text extraction
        ├── ocr.py                  # OCR pipeline
        ├── indexer.py              # Chunking, tagging, metadata
        ├── search.py               # Hybrid search implementation
        ├── embeddings.py           # Embedding model helpers
        ├── frontend/               # React/Vite source
        ├── static/                 # Built frontend assets
        ├── requirements.txt
        ├── Dockerfile
        └── docker-compose.yml
```

## Prerequisites

- Python 3.11+
- Node.js 18+ if working on the frontend source
- Tesseract OCR installed locally
- Ollama for optional local LLM tagging
- Docker if using containerized setup

## Local Setup

```bash
cd Desktop/local_document_system
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Optional Ollama setup:

```bash
ollama pull llama3
```

## Run The App

```bash
cd Desktop/local_document_system
PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True \
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

Open:

```text
http://localhost:8000
```

## Frontend Development

```bash
cd Desktop/local_document_system/frontend
npm install
npm run dev
```

Build frontend assets:

```bash
npm run build
```

## API Routes

| Method | Route | Purpose |
| --- | --- | --- |
| `POST` | `/upload` | Upload and ingest a document |
| `GET` | `/documents` | List indexed documents |
| `GET` | `/documents/{id}/status` | Check ingestion progress |
| `GET` | `/documents/{id}/text` | Read extracted text |
| `GET` | `/documents/{id}/download` | Download the original file |
| `DELETE` | `/documents/{id}` | Remove a document |
| `POST` | `/search` | Search indexed documents |
| `GET` | `/tags` | List available tags |
| `GET` | `/health` | Check service health |
| `POST` | `/retag` | Re-run tagging |
| `POST` | `/reset` | Clear local indexed data |

## Docker

```bash
cd Desktop/local_document_system
docker compose up --build
```

## Notes

Runtime data such as uploaded files, SQLite metadata, and vector-store files are created locally. Keep secrets, large model files, and generated data out of commits unless they are intentionally part of a benchmark or release artifact.
