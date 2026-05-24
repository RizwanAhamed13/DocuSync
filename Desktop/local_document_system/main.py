import asyncio
import json
import os
import shutil
import sqlite3
import uuid
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from embeddings import (
    EMBEDDING_MODEL_NAME,
    get_chroma_client,
    get_chroma_collection,
    get_embedding_model,
    reset_chroma_singleton,
)
from indexer import (
    check_model_version_match,
    check_ollama_availability,
    chunk_document,
    extract_ai_metadata,
    get_db_connection,
    save_model_version,
)
from parser import extract_text_by_pages
from search import hybrid_search

UPLOAD_DIR = "./uploads"
VECTOR_DIR = "./vector_store"

# Both limits are configurable via environment variables
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_SIZE_MB", "50")) * 1024 * 1024
MAX_CHUNKS_PER_DOC = int(os.getenv("MAX_CHUNKS_PER_DOC", "2000"))

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(VECTOR_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# Database initialisation
# ---------------------------------------------------------------------------


def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "CREATE TABLE IF NOT EXISTS db_meta (key TEXT PRIMARY KEY, value TEXT)"
    )
    row = cursor.execute(
        "SELECT value FROM db_meta WHERE key = 'schema_version'"
    ).fetchone()
    schema_version = int(row["value"]) if row else 0

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY,
            filename TEXT NOT NULL,
            file_size_bytes INTEGER NOT NULL,
            page_count INTEGER NOT NULL,
            summary TEXT,
            tags TEXT,
            key_findings TEXT,
            entities TEXT,
            status TEXT DEFAULT 'processing',
            error_message TEXT,
            upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    # Migrate FTS table to porter tokenizer (schema v2)
    if schema_version < 2:
        existing_fts: list = []
        try:
            existing_fts = cursor.execute(
                "SELECT id, filename, text, tags, summary FROM documents_fts"
            ).fetchall()
        except Exception:
            pass

        cursor.execute("DROP TABLE IF EXISTS documents_fts")

        # Try progressively simpler tokenizer options for maximum compatibility
        for ddl in [
            """CREATE VIRTUAL TABLE documents_fts USING fts5(
                   id UNINDEXED, filename, text, tags, summary,
                   tokenize = 'porter unicode61')""",
            """CREATE VIRTUAL TABLE documents_fts USING fts5(
                   id UNINDEXED, filename, text, tags, summary,
                   tokenize = 'porter ascii')""",
            """CREATE VIRTUAL TABLE documents_fts USING fts4(
                   id, filename, text, tags, summary, tokenize=porter)""",
        ]:
            try:
                cursor.execute(ddl)
                break
            except sqlite3.OperationalError:
                continue

        for r in existing_fts:
            cursor.execute(
                "INSERT INTO documents_fts (id, filename, text, tags, summary) VALUES (?, ?, ?, ?, ?)",
                (r["id"], r["filename"], r["text"], r["tags"], r["summary"]),
            )

        cursor.execute(
            "INSERT OR REPLACE INTO db_meta (key, value) VALUES ('schema_version', '2')"
        )
        print(
            f"FTS table migrated to porter tokenizer "
            f"({len(existing_fts)} documents re-indexed)."
        )

    cursor.execute(
        "UPDATE documents SET status = 'failed', "
        "error_message = 'Ingestion interrupted by system restart. Please re-upload.' "
        "WHERE status = 'processing'"
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Application lifespan — startup checks
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()

    # Warn if the embedding model has changed since last run (search quality degrades
    # when queries use a different model than the stored vectors)
    if not check_model_version_match():
        print(
            f"\nWARNING: Embedding model changed to '{EMBEDDING_MODEL_NAME}'. "
            "Existing search results will be inaccurate until you call POST /reset "
            "or POST /migrate-to-cosine (which also re-embeds with the new model). "
            "New uploads will use the new model immediately.\n"
        )

    ollama = await check_ollama_availability()
    if not ollama["available"]:
        print(f"\nWARNING: {ollama['warning']}\n")
    elif ollama.get("warning"):
        print(f"\nWARNING: {ollama['warning']}\n")
    else:
        print(f"Ollama ready. Available models: {', '.join(ollama['models'])}")

    yield  # Application is running


# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------


app = FastAPI(title="Local Document Analyzer & Semantic Search", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SearchRequest(BaseModel):
    query: str
    limit: int = 5


# ---------------------------------------------------------------------------
# Background ingestion pipeline
# ---------------------------------------------------------------------------


async def background_ingest_task(file_path: str, doc_id: str):
    """
    Parse → chunk → embed → AI-tag → persist.
    CPU-bound steps run via asyncio.to_thread to stay off the event loop.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        pages_content = await asyncio.to_thread(extract_text_by_pages, file_path)
        if not pages_content:
            raise ValueError("No extractable text content found in document.")

        filename = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)
        page_count = len(pages_content)

        full_sample = "\n\n".join(p["text"] for p in pages_content[:3])
        ai_metadata = await extract_ai_metadata(full_sample)

        summary = ai_metadata.get("summary", "No summary generated.")
        tags = ai_metadata.get("tags", ["General"])
        key_findings = ai_metadata.get("key_findings", [])
        entities = ai_metadata.get("entities", {})

        chunks = chunk_document(pages_content)

        if len(chunks) > MAX_CHUNKS_PER_DOC:
            print(
                f"{filename}: {len(chunks)} chunks exceeds cap of {MAX_CHUNKS_PER_DOC}. "
                f"Indexing first {MAX_CHUNKS_PER_DOC} chunks only. "
                f"Raise MAX_CHUNKS_PER_DOC env var to index the full document."
            )
            chunks = chunks[:MAX_CHUNKS_PER_DOC]

        if chunks:
            chunk_texts = [c["text"] for c in chunks]
            model = get_embedding_model()
            embeddings_ndarray = await asyncio.to_thread(model.encode, chunk_texts)
            embeddings = embeddings_ndarray.tolist()

            ids = [f"{doc_id}_chunk_{i}" for i in range(len(chunks))]
            metadatas = [{"document_id": doc_id, "page": c["page"]} for c in chunks]

            collection = get_chroma_collection()
            await asyncio.to_thread(
                collection.add,
                ids=ids,
                embeddings=embeddings,
                metadatas=metadatas,
                documents=chunk_texts,
            )

        cursor.execute(
            """
            UPDATE documents
            SET file_size_bytes=?, page_count=?, summary=?, tags=?,
                key_findings=?, entities=?, status='completed'
            WHERE id=?
            """,
            (
                file_size,
                page_count,
                summary,
                json.dumps(tags),
                json.dumps(key_findings),
                json.dumps(entities),
                doc_id,
            ),
        )

        full_text = "\n\n".join(p["text"] for p in pages_content)
        cursor.execute(
            "INSERT OR REPLACE INTO documents_fts (id, filename, text, tags, summary) "
            "VALUES (?, ?, ?, ?, ?)",
            (doc_id, filename, full_text, " ".join(tags), summary),
        )

        conn.commit()
        print(f"Successfully processed: {filename}")

    except Exception as exc:
        conn.rollback()
        error_msg = str(exc)
        print(f"Ingestion failed for {file_path}: {error_msg}")
        cursor.execute(
            "UPDATE documents SET status='failed', error_message=? WHERE id=?",
            (error_msg, doc_id),
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------


@app.get("/health")
async def health_check():
    """System health: Ollama status, storage counts, model configuration."""
    conn = get_db_connection()
    doc_count = conn.execute(
        "SELECT COUNT(*) as c FROM documents WHERE status='completed'"
    ).fetchone()["c"]
    processing_count = conn.execute(
        "SELECT COUNT(*) as c FROM documents WHERE status='processing'"
    ).fetchone()["c"]
    conn.close()

    collection = get_chroma_collection()
    chunk_count = collection.count()
    space = (collection.metadata or {}).get("hnsw:space", "l2")

    ollama_status = await check_ollama_availability()

    return {
        "status": "ok",
        "documents": {"indexed": doc_count, "processing": processing_count},
        "vector_store": {
            "chunks": chunk_count,
            "distance_space": space,
            "needs_cosine_migration": space != "cosine" and chunk_count > 0,
        },
        "embedding_model": EMBEDDING_MODEL_NAME,
        "limits": {
            "max_upload_mb": MAX_UPLOAD_BYTES // (1024 * 1024),
            "max_chunks_per_doc": MAX_CHUNKS_PER_DOC,
        },
        "ollama": ollama_status,
    }


@app.post("/reset")
def reset_system():
    """Clears all documents from every store and the uploads folder."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        if os.path.exists(UPLOAD_DIR):
            for f in os.listdir(UPLOAD_DIR):
                fp = os.path.join(UPLOAD_DIR, f)
                if os.path.isfile(fp):
                    os.remove(fp)

        collection = get_chroma_collection()
        results = collection.get()
        if results and results["ids"]:
            collection.delete(ids=results["ids"])

        cursor.execute("DELETE FROM documents")
        cursor.execute("DELETE FROM documents_fts")
        conn.commit()
        save_model_version()
    except Exception as exc:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Reset failed: {exc}")
    finally:
        conn.close()
    return {"message": "System reset successfully."}


@app.post("/migrate-to-cosine")
async def migrate_to_cosine():
    """
    Migrates the ChromaDB collection from L2 to cosine distance in-place.

    Extracts the stored embedding vectors, deletes the old collection, recreates
    it with cosine space, and re-inserts — no re-ingestion needed.  Also runs if
    the embedding model has changed (use /reset instead if you need a full re-index).
    """
    collection = get_chroma_collection()
    current_space = (collection.metadata or {}).get("hnsw:space", "l2")

    if current_space == "cosine":
        return {"message": "Collection already uses cosine distance. No migration needed."}

    items = collection.get(include=["embeddings", "documents", "metadatas"])
    item_count = len(items.get("ids") or [])

    client = get_chroma_client()
    client.delete_collection("document_chunks")
    reset_chroma_singleton()

    new_collection = get_chroma_collection()  # recreated with cosine space

    if item_count > 0:
        await asyncio.to_thread(
            new_collection.add,
            ids=items["ids"],
            embeddings=items["embeddings"],
            documents=items["documents"],
            metadatas=items["metadatas"],
        )

    return {
        "message": f"Migrated {item_count} chunks to cosine distance space.",
        "chunks_preserved": item_count,
    }


@app.post("/upload")
async def upload_file(
    background_tasks: BackgroundTasks, file: UploadFile = File(...)
):
    """Saves a document to disk and starts background ingestion."""
    allowed_extensions = {".pdf", ".docx", ".txt", ".md", ".json"}
    _, ext = os.path.splitext(file.filename.lower())

    if ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format. Allowed: {', '.join(allowed_extensions)}",
        )

    doc_id = str(uuid.uuid4())
    temp_path = os.path.join(UPLOAD_DIR, f"{doc_id}{ext}")

    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Check size after writing to avoid reading the whole file into memory
    file_size = os.path.getsize(temp_path)
    if file_size > MAX_UPLOAD_BYTES:
        os.remove(temp_path)
        raise HTTPException(
            status_code=413,
            detail=(
                f"File too large ({file_size // (1024 * 1024)} MB). "
                f"Maximum: {MAX_UPLOAD_BYTES // (1024 * 1024)} MB. "
                f"Set MAX_UPLOAD_SIZE_MB env var to raise the limit."
            ),
        )

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO documents (id, filename, file_size_bytes, page_count, status) "
        "VALUES (?, ?, 0, 0, 'processing')",
        (doc_id, file.filename),
    )
    conn.commit()
    conn.close()

    background_tasks.add_task(background_ingest_task, temp_path, doc_id)
    return {"message": "Upload accepted. Processing started.", "document_id": doc_id}


@app.get("/documents")
def list_documents():
    """Returns all documents, newest first."""
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT id, filename, file_size_bytes, page_count, summary, tags, "
        "key_findings, entities, status, error_message, upload_date "
        "FROM documents ORDER BY upload_date DESC"
    ).fetchall()
    conn.close()

    return [
        {
            "id": r["id"],
            "filename": r["filename"],
            "file_size_bytes": r["file_size_bytes"],
            "page_count": r["page_count"],
            "summary": r["summary"],
            "tags": json.loads(r["tags"]) if r["tags"] else [],
            "key_findings": json.loads(r["key_findings"]) if r["key_findings"] else [],
            "entities": json.loads(r["entities"]) if r["entities"] else {},
            "status": r["status"],
            "error_message": r["error_message"],
            "upload_date": r["upload_date"],
        }
        for r in rows
    ]


@app.get("/documents/{doc_id}/status")
def get_document_status(doc_id: str):
    """Lightweight endpoint for polling ingestion progress after upload."""
    conn = get_db_connection()
    row = conn.execute(
        "SELECT status, error_message FROM documents WHERE id=?", (doc_id,)
    ).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Document not found.")
    return {
        "document_id": doc_id,
        "status": row["status"],
        "error_message": row["error_message"],
    }


@app.get("/tags")
def list_tags():
    """Returns unique tags and their document counts."""
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT tags FROM documents WHERE status='completed'"
    ).fetchall()
    conn.close()

    tag_counts: dict[str, int] = {}
    for r in rows:
        if r["tags"]:
            for tag in json.loads(r["tags"]):
                tag_counts[tag] = tag_counts.get(tag, 0) + 1

    return [{"name": name, "count": count} for name, count in tag_counts.items()]


@app.post("/search")
def search_documents(request: SearchRequest):
    """Performs hybrid semantic + keyword search."""
    if not request.query.strip():
        return []
    return hybrid_search(request.query, limit=request.limit)


@app.get("/documents/{doc_id}/text")
def get_document_text(doc_id: str):
    """Returns the full indexed text of a document."""
    conn = get_db_connection()
    row = conn.execute(
        "SELECT text FROM documents_fts WHERE id=?", (doc_id,)
    ).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Document text not found.")
    return {"text": row["text"]}


@app.get("/documents/{doc_id}/download")
def download_original_document(doc_id: str):
    """Serves the original uploaded file."""
    conn = get_db_connection()
    row = conn.execute(
        "SELECT filename FROM documents WHERE id=?", (doc_id,)
    ).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Document not found.")

    filename = row["filename"]
    _, ext = os.path.splitext(filename.lower())
    file_path = os.path.join(UPLOAD_DIR, f"{doc_id}{ext}")

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Original file not found on disk.")

    return FileResponse(
        path=file_path, filename=filename, media_type="application/octet-stream"
    )


@app.delete("/documents/{doc_id}")
def delete_document(doc_id: str):
    """Removes a document from all stores."""
    conn = get_db_connection()
    cursor = conn.cursor()

    row = cursor.execute(
        "SELECT filename FROM documents WHERE id=?", (doc_id,)
    ).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Document not found.")

    filename = row["filename"]

    try:
        for ext in [".pdf", ".docx", ".txt", ".md", ".json"]:
            path = os.path.join(UPLOAD_DIR, f"{doc_id}{ext}")
            if os.path.exists(path):
                os.remove(path)
                break

        get_chroma_collection().delete(where={"document_id": doc_id})

        cursor.execute("DELETE FROM documents WHERE id=?", (doc_id,))
        cursor.execute("DELETE FROM documents_fts WHERE id=?", (doc_id,))
        conn.commit()
    except Exception as exc:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Delete failed: {exc}")
    finally:
        conn.close()

    return {"message": f"Successfully deleted {filename}"}


# Serve the SPA frontend
os.makedirs("./static", exist_ok=True)
app.mount("/", StaticFiles(directory="./static", html=True), name="static")
