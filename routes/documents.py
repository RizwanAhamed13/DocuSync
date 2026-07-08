"""
Document routes — upload, list, status, text, download, delete, retry.
"""
from __future__ import annotations
from typing import Optional
import asyncio
import json
import os
import re
import shutil
import uuid

import numpy as np
from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from core.config import ALLOWED_EXTENSIONS, MAX_CHUNKS_PER_DOC, MAX_UPLOAD_BYTES, UPLOAD_DIR
from core.db import get_db_connection
from services.embeddings import get_chroma_collection, get_embedding_model
from services.indexer import (
    _rule_based_tags,
    _rule_based_summary,
    chunk_document,
    extract_ai_metadata,
    extract_key_insights,
)
from services.ocr import warm_up_ocr  # noqa: F401  (imported in lifespan)
from services.parser import extract_text_by_pages

router = APIRouter()

# ── Serialise AI inference to avoid GPU memory contention ─────────────────────
# Running DeBERTa + DistilBART concurrently on the same MPS/CUDA device causes
# "meta tensor" errors when models are half-initialised. One ingest at a time.
_AI_SEMAPHORE = asyncio.Semaphore(3)

# ── In-memory progress tracker (resets on restart) ────────────────────────────
_ingest_progress: dict[str, dict] = {}


def get_ingest_progress() -> dict[str, dict]:
    return _ingest_progress


def _set_progress(doc_id: str, step: str, pct: int, detail: str = "") -> None:
    _ingest_progress[doc_id] = {"step": step, "pct": pct, "detail": detail}


# ── Tag / doc-type helpers ────────────────────────────────────────────────────

_SYLLABUS_TAGS = {"Course Syllabus", "Syllabus"}
_NOTES_TAGS    = {"Lecture Notes", "Lab Report", "Lab Notes"}
_ASSIGN_TAGS   = {"Assignment", "Final Exam", "Midterm Exam", "Exam / Quiz",
                  "Question Bank", "Homework", "Project"}
_LEVEL_WORDS   = ("Graduate", "Doctoral", "Undergraduate", "Upper", "Sophomore",
                  "Introductory", "Advanced")
_TERM_RE       = re.compile(r"^(Spring|Fall|Summer|Winter)\s+\d{4}$", re.IGNORECASE)


def _classify_doc_type(tags: list[str]) -> str:
    tag_set = set(tags)
    if tag_set & _SYLLABUS_TAGS:
        return "syllabus"
    if tag_set & _NOTES_TAGS:
        return "notes"
    if tag_set & _ASSIGN_TAGS:
        return "assign"
    return "other"


def _categorise_tags(tags: list[str]) -> dict:
    DOC_TYPE_SET = _SYLLABUS_TAGS | _NOTES_TAGS | _ASSIGN_TAGS
    result: dict[str, list[str]] = {"subject": [], "doc_type": [], "level": [], "term": []}
    for t in tags:
        if t in DOC_TYPE_SET:
            result["doc_type"].append(t)
        elif _TERM_RE.match(t):
            result["term"].append(t)
        elif any(w in t for w in _LEVEL_WORDS):
            result["level"].append(t)
        else:
            result["subject"].append(t)
    return result


# ── Background ingestion pipeline ─────────────────────────────────────────────

async def background_ingest_task(file_path: str, doc_id: str) -> None:
    conn = None
    cursor = None
    try:
        _set_progress(doc_id, "parsing", 5, "Reading document pages…")

        def _page_cb(current: int, total: int) -> None:
            pct = 5 + int((current / max(total, 1)) * 60)
            _set_progress(doc_id, "parsing", pct, f"Reading page {current}/{total}…")

        pages_content = await asyncio.to_thread(
            extract_text_by_pages, file_path, _page_cb
        )
        if not pages_content:
            raise ValueError("No extractable text content found in document.")

        filename    = os.path.basename(file_path)
        file_size   = os.path.getsize(file_path)
        page_count  = len(pages_content)
        full_sample = "\n\n".join(p["text"] for p in pages_content[:3])

        _set_progress(doc_id, "ai_tagging", 65,
                      f"Running AI analysis on {page_count} page{'s' if page_count != 1 else ''}…")
        # Serialise GPU inference — only one doc at a time to avoid meta-tensor errors
        async with _AI_SEMAPHORE:
            ai_metadata = await extract_ai_metadata(full_sample, filename=filename)

        summary         = ai_metadata.get("summary", "No summary generated.")
        tags            = ai_metadata.get("tags", ["Document"])
        classifications = ai_metadata.get("classifications", {})
        key_findings    = ai_metadata.get("key_findings", [])
        entities        = ai_metadata.get("entities", {})

        _set_progress(doc_id, "chunking", 70, "Splitting into searchable chunks…")
        chunks = chunk_document(pages_content)

        if len(chunks) > MAX_CHUNKS_PER_DOC:
            print(f"{filename}: capping at {MAX_CHUNKS_PER_DOC} chunks (was {len(chunks)})")
            chunks = chunks[:MAX_CHUNKS_PER_DOC]

        if chunks:
            chunk_texts = [c["text"] for c in chunks]
            _set_progress(doc_id, "embedding", 76,
                          f"Generating vectors for {len(chunks)} chunks…")
            model = get_embedding_model()
            embeddings_ndarray = await asyncio.to_thread(model.encode, chunk_texts)

            valid_mask = np.all(np.isfinite(embeddings_ndarray), axis=1)
            if not np.all(valid_mask):
                bad = int((~valid_mask).sum())
                print(f"{filename}: dropping {bad} chunk(s) with NaN/Inf embeddings")
                chunks             = [c for c, v in zip(chunks, valid_mask) if v]
                chunk_texts        = [t for t, v in zip(chunk_texts, valid_mask) if v]
                embeddings_ndarray = embeddings_ndarray[valid_mask]

            ids       = [f"{doc_id}_chunk_{i}" for i in range(len(chunks))]
            metadatas = [{"document_id": doc_id, "page": c["page"]} for c in chunks]

            collection = get_chroma_collection()
            _set_progress(doc_id, "saving", 93, "Writing to vector index…")
            await asyncio.to_thread(
                collection.add,
                ids=ids,
                embeddings=embeddings_ndarray.tolist(),
                metadatas=metadatas,
                documents=chunk_texts,
            )

        _set_progress(doc_id, "saving", 97, "Persisting metadata to database…")
        cls_doc_types = classifications.get("doc_type", [])
        doc_type = _classify_doc_type(cls_doc_types) if cls_doc_types else _classify_doc_type(tags)

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE documents
            SET file_size_bytes=?, page_count=?, summary=?, tags=?,
                classifications=?, key_findings=?, entities=?, doc_type=?, status='completed'
            WHERE id=?
            """,
            (
                file_size, page_count, summary,
                json.dumps(tags), json.dumps(classifications),
                json.dumps(key_findings), json.dumps(entities),
                doc_type, doc_id,
            ),
        )
        full_text = "\n\n".join(p["text"] for p in pages_content)
        cursor.execute(
            "INSERT OR REPLACE INTO documents_fts (id, filename, text, tags, summary) "
            "VALUES (?, ?, ?, ?, ?)",
            (doc_id, filename, full_text, " ".join(tags), summary),
        )
        conn.commit()
        _ingest_progress.pop(doc_id, None)
        print(f"Successfully processed: {filename}")

    except Exception as exc:
        if conn is not None:
            conn.rollback()
        print(f"Ingestion failed for {file_path}: {exc}")
        _ingest_progress.pop(doc_id, None)
        try:
            fail_conn = get_db_connection()
            fail_conn.execute(
                "UPDATE documents SET status='failed', error_message=? WHERE id=?",
                (str(exc), doc_id),
            )
            fail_conn.commit()
            fail_conn.close()
        except Exception:
            pass
    finally:
        if conn is not None:
            conn.close()


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/upload")
async def upload_file(
    background_tasks: BackgroundTasks, file: UploadFile = File(...)
):
    """Saves a document to disk and starts background ingestion."""
    _, ext = os.path.splitext(file.filename.lower())
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    doc_id    = str(uuid.uuid4())
    temp_path = os.path.join(UPLOAD_DIR, f"{doc_id}{ext}")

    with open(temp_path, "wb") as buf:
        shutil.copyfileobj(file.file, buf)

    file_size = os.path.getsize(temp_path)
    if file_size > MAX_UPLOAD_BYTES:
        os.remove(temp_path)
        raise HTTPException(
            status_code=413,
            detail=(
                f"File too large ({file_size // (1024 * 1024)} MB). "
                f"Max: {MAX_UPLOAD_BYTES // (1024 * 1024)} MB "
                f"(set MAX_UPLOAD_SIZE_MB to raise)."
            ),
        )

    conn = get_db_connection()
    conn.execute(
        "INSERT INTO documents (id, filename, file_size_bytes, page_count, status) "
        "VALUES (?, ?, 0, 0, 'processing')",
        (doc_id, file.filename),
    )
    conn.commit()
    conn.close()

    background_tasks.add_task(background_ingest_task, temp_path, doc_id)
    return {"message": "Upload accepted. Processing started.", "document_id": doc_id}


@router.get("/documents")
def list_documents(
    type:      Optional[str] = Query(None, description="Legacy doc_type filter: syllabus|notes|assign|other"),
    tag:       Optional[str] = Query(None, description="Filter by keyword tag"),
    dimension: Optional[str] = Query(None, description="Perspective: subject|field|doc_type|methodology"),
    value:     Optional[str] = Query(None, description="Classification value within the dimension"),
):
    """Returns all documents, newest first. Supports tag, type, and dimension/value filters."""
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT id, filename, file_size_bytes, page_count, summary, tags, "
        "classifications, key_findings, entities, doc_type, status, error_message, upload_date "
        "FROM documents ORDER BY upload_date DESC"
    ).fetchall()
    conn.close()

    results = []
    for r in rows:
        tags_list = json.loads(r["tags"]) if r["tags"] else []
        cls       = json.loads(r["classifications"]) if r["classifications"] else {}
        doc_type  = r["doc_type"] or _classify_doc_type(tags_list)

        if type and doc_type != type:
            continue
        if tag and tag not in tags_list:
            continue
        if dimension and value and value not in cls.get(dimension, []):
            continue

        results.append({
            "id":              r["id"],
            "filename":        r["filename"],
            "file_size_bytes": r["file_size_bytes"],
            "page_count":      r["page_count"],
            "summary":         r["summary"],
            "tags":            tags_list,
            "classifications": cls,
            "tag_categories":  _categorise_tags(tags_list),
            "doc_type":        doc_type,
            "key_findings":    json.loads(r["key_findings"]) if r["key_findings"] else [],
            "entities":        json.loads(r["entities"])     if r["entities"]     else {},
            "status":          r["status"],
            "error_message":   r["error_message"],
            "upload_date":     r["upload_date"],
        })
    return results


@router.get("/documents/counts")
def document_counts():
    """Per-category document counts for sidebar badges."""
    conn  = get_db_connection()
    rows  = conn.execute("SELECT doc_type, status FROM documents").fetchall()
    conn.close()
    counts = {"all": 0, "syllabus": 0, "notes": 0, "assign": 0, "other": 0,
              "processing": 0, "failed": 0}
    for r in rows:
        if r["status"] == "processing":
            counts["processing"] += 1
        elif r["status"] == "failed":
            counts["failed"] += 1
        elif r["status"] == "completed":
            counts["all"] += 1
            dt = r["doc_type"] or "other"
            if dt in counts:
                counts[dt] += 1
    return counts


@router.get("/documents/{doc_id}/status")
def get_document_status(doc_id: str):
    """Lightweight polling endpoint for ingestion progress."""
    conn = get_db_connection()
    row  = conn.execute(
        "SELECT status, error_message FROM documents WHERE id=?", (doc_id,)
    ).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Document not found.")

    prog   = _ingest_progress.get(doc_id, {})
    status = row["status"]
    return {
        "document_id":  doc_id,
        "status":       status,
        "error_message": row["error_message"],
        "step":   prog.get("step",   "queued" if status == "processing" else status),
        "pct":    prog.get("pct",    0 if status == "processing" else (100 if status == "completed" else 0)),
        "detail": prog.get("detail", "Waiting to start…" if status == "processing" else ""),
    }


@router.get("/documents/{doc_id}/text")
def get_document_text(doc_id: str):
    """Returns the full indexed text of a document."""
    conn = get_db_connection()
    row  = conn.execute("SELECT text FROM documents_fts WHERE id=?", (doc_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Document text not found.")
    return {"text": row["text"]}


@router.get("/documents/{doc_id}/insights")
def get_document_insights(doc_id: str):
    """
    Returns key insight sentences extracted from the document's indexed text.
    Uses stored key_findings if available; otherwise extracts on-demand from FTS text.
    """
    conn = get_db_connection()
    meta = conn.execute(
        "SELECT key_findings FROM documents WHERE id=? AND status='completed'", (doc_id,)
    ).fetchone()
    fts  = conn.execute("SELECT text FROM documents_fts WHERE id=?", (doc_id,)).fetchone()
    conn.close()

    if not meta:
        raise HTTPException(status_code=404, detail="Document not found.")

    # Always extract fresh from full text using the scientific-signal extractor
    # (stored key_findings used policy/syllabus heuristics — not suitable for research papers)
    text = fts["text"] if fts else ""
    if not text.strip():
        return {"insights": [], "source": "none"}

    return {"insights": extract_key_insights(text, n=5), "source": "extracted"}


@router.get("/documents/{doc_id}/download")
def download_original_document(doc_id: str):
    """Serves the original uploaded file."""
    conn = get_db_connection()
    row  = conn.execute("SELECT filename FROM documents WHERE id=?", (doc_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Document not found.")

    filename = row["filename"]
    _, ext   = os.path.splitext(filename.lower())
    path     = os.path.join(UPLOAD_DIR, f"{doc_id}{ext}")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Original file not found on disk.")
    return FileResponse(path=path, filename=filename, media_type="application/octet-stream")


@router.delete("/documents/{doc_id}")
def delete_document(doc_id: str):
    """Removes a document from all stores."""
    conn   = get_db_connection()
    cursor = conn.cursor()
    row    = cursor.execute("SELECT filename FROM documents WHERE id=?", (doc_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Document not found.")

    filename = row["filename"]
    try:
        for ext in ALLOWED_EXTENSIONS:
            p = os.path.join(UPLOAD_DIR, f"{doc_id}{ext}")
            if os.path.exists(p):
                os.remove(p)
                break
        get_chroma_collection().delete(where={"document_id": doc_id})
        cursor.execute("DELETE FROM documents     WHERE id=?", (doc_id,))
        cursor.execute("DELETE FROM documents_fts WHERE id=?", (doc_id,))
        conn.commit()
    except Exception as exc:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Delete failed: {exc}")
    finally:
        conn.close()
    return {"message": f"Deleted {filename}"}


@router.post("/documents/{doc_id}/retry")
async def retry_failed_document(doc_id: str, background_tasks: BackgroundTasks):
    """Re-queue a failed document for ingestion without re-uploading the file."""
    conn = get_db_connection()
    row  = conn.execute(
        "SELECT filename, status FROM documents WHERE id=?", (doc_id,)
    ).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Document not found.")
    if row["status"] not in ("failed", "processing"):
        conn.close()
        raise HTTPException(
            status_code=400,
            detail=f"Status is '{row['status']}' — only failed documents can be retried.",
        )

    filename  = row["filename"]
    _, ext    = os.path.splitext(filename.lower())
    file_path = os.path.join(UPLOAD_DIR, f"{doc_id}{ext}")
    if not os.path.exists(file_path):
        conn.close()
        raise HTTPException(status_code=404, detail="Original file not found on disk. Please re-upload.")

    conn.execute(
        "UPDATE documents SET status='processing', error_message=NULL WHERE id=?", (doc_id,)
    )
    conn.commit()
    conn.close()
    background_tasks.add_task(background_ingest_task, file_path, doc_id)
    return {"message": f"Retry started for {filename}.", "document_id": doc_id}
