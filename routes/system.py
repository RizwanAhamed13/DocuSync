"""
System management routes — health, reset, retag, cosine migration.
"""
from __future__ import annotations
from typing import Optional
import asyncio
import json
import os

from fastapi import APIRouter, HTTPException

from core.config import MAX_CHUNKS_PER_DOC, MAX_UPLOAD_BYTES, UPLOAD_DIR
from core.db import get_db_connection
from services.embeddings import (
    EMBEDDING_MODEL_NAME,
    get_chroma_client,
    get_chroma_collection,
    reset_chroma_singleton,
)
from services.indexer import (
    _classify_dimensions,
    _extract_keyword_tags,
    _rule_based_summary,
    _rule_based_tags,
    check_model_version_match,
    classifier_needs_reindex,
    get_classifier_signature,
    save_classifier_signature,
    save_model_version,
    _CLASSIFIER_SIGNATURE,
)

router = APIRouter()


@router.get("/health")
async def health_check():
    """System health: storage counts, model info, vector store state."""
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
            "max_upload_mb":    MAX_UPLOAD_BYTES // (1024 * 1024),
            "max_chunks_per_doc": MAX_CHUNKS_PER_DOC,
        },
    }


@router.post("/reset")
def reset_system():
    """Clears all documents from every store and the uploads folder."""
    conn   = get_db_connection()
    cursor = conn.cursor()
    try:
        if os.path.exists(UPLOAD_DIR):
            for f in os.listdir(UPLOAD_DIR):
                fp = os.path.join(UPLOAD_DIR, f)
                if os.path.isfile(fp):
                    os.remove(fp)

        collection = get_chroma_collection()
        results    = collection.get()
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


@router.post("/retag")
def retag_documents(force: bool = False):
    """
    Re-apply rule-based tags and summaries.
    force=false: only fixes documents with missing/generic tags.
    force=true:  retags every completed document.
    """
    conn = get_db_connection()

    if force:
        rows = conn.execute(
            "SELECT d.id, d.filename, f.text "
            "FROM documents d LEFT JOIN documents_fts f ON d.id = f.id "
            "WHERE d.status = 'completed'"
        ).fetchall()
        updated = 0
        for row in rows:
            text    = row["text"] or ""
            tags    = _rule_based_tags(row["filename"], text)
            summary = _rule_based_summary(row["filename"], text)
            conn.execute(
                "UPDATE documents SET tags=?, summary=? WHERE id=?",
                (json.dumps(tags), summary, row["id"]),
            )
            updated += 1
        conn.commit()
        conn.close()
        return {"message": f"Force-retagged {updated} documents.", "updated": updated}

    # Partial: fix only broken/empty entries
    rows = conn.execute(
        "SELECT d.id, d.filename, d.tags, d.summary, f.text "
        "FROM documents d LEFT JOIN documents_fts f ON d.id = f.id "
        "WHERE d.tags IN ('[\"Uncategorized\"]','[\"General\"]','[]') "
        "   OR d.tags IS NULL "
        "   OR d.summary IS NULL OR d.summary = '' "
        "   OR d.summary LIKE 'AI summary%'"
    ).fetchall()
    updated = 0
    for row in rows:
        text    = row["text"] or ""
        tags    = _rule_based_tags(row["filename"], text)
        summary = _rule_based_summary(row["filename"], text)
        conn.execute(
            "UPDATE documents SET tags=?, summary=? WHERE id=?",
            (json.dumps(tags), summary, row["id"]),
        )
        updated += 1
    if updated:
        conn.commit()
    conn.close()
    return {"message": f"Retagged {updated} document(s).", "updated": updated}


@router.get("/classifier-status")
def classifier_status():
    """Return whether the stored classifier signature matches current config."""
    stored = get_classifier_signature()
    needs_reindex = stored != "" and stored != _CLASSIFIER_SIGNATURE
    return {
        "current_signature": _CLASSIFIER_SIGNATURE,
        "stored_signature":  stored or "(not set)",
        "needs_reindex":     needs_reindex,
        "message": (
            "Classifier config changed — run POST /retag-ai to re-classify all docs."
            if needs_reindex else "Classifier up to date."
        ),
    }


_retag_running = False


@router.post("/retag-ai")
async def retag_ai(force: bool = False, limit: Optional[int] = None):
    """
    Re-run DeBERTa classification + keyword extraction on all (or unclassified) docs.
    This is the equivalent of running scripts/retag_scifact.py from the API.
    Runs in a background thread so the response returns immediately.
    """
    global _retag_running
    if _retag_running:
        return {"message": "Re-tag already in progress.", "status": "running"}

    async def _bg():
        global _retag_running
        _retag_running = True
        try:
            conn = get_db_connection()
            if force:
                query = (
                    "SELECT d.id, d.filename, f.text FROM documents d "
                    "LEFT JOIN documents_fts f ON d.id = f.id WHERE d.status='completed'"
                )
            else:
                query = (
                    "SELECT d.id, d.filename, f.text FROM documents d "
                    "LEFT JOIN documents_fts f ON d.id = f.id "
                    "WHERE d.status='completed' "
                    "AND (d.classifications IS NULL OR d.classifications='{}' OR d.classifications='')"
                )
            rows = conn.execute(query).fetchall()
            if limit:
                rows = rows[:limit]
            total = len(rows)
            print(f"[retag-ai] Starting re-tag of {total} documents…")

            import re as _re
            updated = 0
            for i, row in enumerate(rows, 1):
                text = (row["text"] or "")[:1500]
                if not text.strip():
                    continue
                try:
                    cls = await asyncio.to_thread(_classify_dimensions, text, row["filename"])
                    kw_tags = await asyncio.to_thread(_extract_keyword_tags, text, row["filename"])
                    sents = [s.strip() for s in _re.split(r"(?<=[.!?])\s+", (row["text"] or "")[:600]) if len(s.strip()) > 20]
                    summary = " ".join(sents[:2])
                    if len(summary) > 280:
                        summary = summary[:277] + "…"
                    conn.execute(
                        "UPDATE documents SET classifications=?, tags=?, summary=? WHERE id=?",
                        (json.dumps(cls), json.dumps(kw_tags), summary, row["id"]),
                    )
                    updated += 1
                    if updated % 50 == 0:
                        conn.commit()
                        print(f"[retag-ai] {updated}/{total} done")
                except Exception as e:
                    print(f"[retag-ai] SKIP {row['filename']}: {e}")

            conn.commit()
            conn.close()
            save_classifier_signature()
            print(f"[retag-ai] Complete — {updated}/{total} documents updated.")
        finally:
            _retag_running = False

    asyncio.create_task(_bg())
    return {
        "message": "Re-classification started in background.",
        "status": "started",
        "note": "Check /classifier-status to see when it completes.",
    }


@router.post("/migrate-to-cosine")
async def migrate_to_cosine():
    """Migrate ChromaDB collection from L2 to cosine distance in-place."""
    collection    = get_chroma_collection()
    current_space = (collection.metadata or {}).get("hnsw:space", "l2")

    if current_space == "cosine":
        return {"message": "Collection already uses cosine distance. No migration needed."}

    items      = collection.get(include=["embeddings", "documents", "metadatas"])
    item_count = len(items.get("ids") or [])

    client = get_chroma_client()
    client.delete_collection("document_chunks")
    reset_chroma_singleton()

    new_collection = get_chroma_collection()
    if item_count > 0:
        await asyncio.to_thread(
            new_collection.add,
            ids=items["ids"],
            embeddings=items["embeddings"],
            documents=items["documents"],
            metadatas=items["metadatas"],
        )

    return {
        "message":         f"Migrated {item_count} chunks to cosine distance space.",
        "chunks_preserved": item_count,
    }
