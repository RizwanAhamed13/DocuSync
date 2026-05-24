import json
import re
import sqlite3

from embeddings import get_chroma_collection, get_embedding_model
from indexer import get_db_connection


def get_document_metadata(doc_id: str) -> dict | None:
    conn = get_db_connection()
    cursor = conn.cursor()
    row = cursor.execute(
        "SELECT filename, summary, tags, key_findings, entities FROM documents WHERE id = ?",
        (doc_id,),
    ).fetchone()
    conn.close()
    if row:
        return {
            "filename": row["filename"],
            "summary": row["summary"],
            "tags": json.loads(row["tags"]) if row["tags"] else [],
            "key_findings": json.loads(row["key_findings"]) if row["key_findings"] else [],
            "entities": json.loads(row["entities"]) if row["entities"] else {},
        }
    return None


def _fts_keyword_ranks(query_text: str) -> dict[str, int]:
    """
    Returns {doc_id: rank} for BM25-ranked FTS5 results (1-indexed, lower = better).
    Terms shorter than 3 chars are skipped to avoid noise.
    """
    terms = [t for t in re.findall(r"\w+", query_text.lower()) if len(t) > 1]
    if not terms:
        return {}

    fts_query = " OR ".join(terms)
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        rows = cursor.execute(
            "SELECT id FROM documents_fts WHERE text MATCH ? ORDER BY bm25(documents_fts) LIMIT 20",
            (fts_query,),
        ).fetchall()
        return {r["id"]: rank + 1 for rank, r in enumerate(rows)}
    except Exception as exc:
        print(f"FTS5 error for '{fts_query}': {exc}")
        return {}
    finally:
        conn.close()


def hybrid_search(query_text: str, limit: int = 5) -> list[dict]:
    """
    Hybrid search: vector similarity (ChromaDB) + BM25 keyword (SQLite FTS5),
    fused via Reciprocal Rank Fusion (RRF, k=60).

    RRF score = 1/(k + semantic_rank) + 1/(k + keyword_rank)
    Documents absent from keyword results receive a penalty rank so semantic
    relevance still drives ordering when keyword search finds nothing.
    """
    RRF_K = 60

    # --- 1. Keyword ranks (FTS5 BM25) ---
    keyword_ranks = _fts_keyword_ranks(query_text)
    # Penalty rank for docs not found by keyword search
    kw_penalty = len(keyword_ranks) + RRF_K

    # --- 2. Semantic search (ChromaDB) ---
    model = get_embedding_model()
    collection = get_chroma_collection()

    total_chunks = collection.count()
    if total_chunks == 0:
        return []

    n_results = min(40, total_chunks)
    vector_results = collection.query(
        query_embeddings=[model.encode(query_text).tolist()],
        n_results=n_results,
    )

    if not vector_results or not vector_results["ids"] or not vector_results["ids"][0]:
        return []

    # Determine distance space so similarity is reported correctly.
    # New collections use cosine (dist = 1 - cos_sim).
    # Existing L2 collections use unit-normalised vectors so:
    #   cos_sim = 1 - dist² / 2
    collection_space = (collection.metadata or {}).get("hnsw:space", "l2")

    # --- 3. Build chunks with RRF scores ---
    metadata_cache: dict[str, dict | None] = {}

    def get_cached_meta(doc_id: str) -> dict | None:
        if doc_id not in metadata_cache:
            metadata_cache[doc_id] = get_document_metadata(doc_id)
        return metadata_cache[doc_id]

    chunks = []
    for sem_rank, (chunk_id, distance, meta, text) in enumerate(
        zip(
            vector_results["ids"][0],
            vector_results["distances"][0],
            vector_results["metadatas"][0],
            vector_results["documents"][0],
        ),
        start=1,
    ):
        doc_id = meta["document_id"]
        kw_rank = keyword_ranks.get(doc_id, kw_penalty)

        rrf_score = 1.0 / (RRF_K + sem_rank) + 1.0 / (RRF_K + kw_rank)

        if collection_space == "cosine":
            cos_sim = max(0.0, 1.0 - distance)
        else:
            # Correct formula for unit-normalised vectors under L2 distance
            cos_sim = max(0.0, 1.0 - distance**2 / 2.0)

        chunks.append(
            {
                "chunk_id": chunk_id,
                "document_id": doc_id,
                "page": meta["page"],
                "text": text,
                "score": round(rrf_score, 6),
                "similarity": round(cos_sim, 4),
            }
        )

    # --- 4. Sort by RRF score, attach metadata, deduplicate ---
    chunks.sort(key=lambda x: x["score"], reverse=True)

    seen: set[str] = set()
    results: list[dict] = []
    for chunk in chunks:
        if chunk["chunk_id"] in seen:
            continue
        seen.add(chunk["chunk_id"])

        doc_meta = get_cached_meta(chunk["document_id"])
        if not doc_meta:
            continue
        chunk.update(doc_meta)
        results.append(chunk)

        if len(results) >= limit:
            break

    return results
