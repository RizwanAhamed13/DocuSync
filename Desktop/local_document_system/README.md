# DocuSync

A local document analyzer and semantic search system.

Upload PDFs, DOCX, and text files — DocuSync parses, chunks, embeds, and AI-tags them locally. Search across all documents using hybrid semantic + keyword retrieval (no cloud services required).

## Stack

- **FastAPI** — REST API + static SPA host
- **ChromaDB** — vector store (cosine similarity, HNSW index)
- **SentenceTransformers** — `all-MiniLM-L6-v2` local embeddings
- **SQLite FTS5** — BM25 keyword search with porter stemmer
- **Ollama** — local LLM (llama3 / phi3) for AI summaries and tagging
- **PyMuPDF + PaddleOCR / Tesseract** — PDF parsing with OCR fallback

## Quick Start

```bash
pip install -r requirements.txt
ollama pull llama3          # or phi3
uvicorn main:app --reload
# open http://localhost:8000
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | SentenceTransformers model name |
| `MAX_UPLOAD_SIZE_MB` | `50` | Max file size per upload |
| `MAX_CHUNKS_PER_DOC` | `2000` | Chunk cap per document |

## API

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/upload` | Upload a document |
| `GET` | `/documents` | List all indexed documents |
| `GET` | `/documents/{id}/status` | Poll ingestion status |
| `POST` | `/search` | Hybrid semantic + keyword search |
| `GET` | `/health` | System health and Ollama status |
| `POST` | `/migrate-to-cosine` | Migrate ChromaDB to cosine space |
| `POST` | `/reset` | Clear all documents and vectors |
