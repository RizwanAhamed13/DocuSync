import json
import os
import re
import sqlite3
from functools import lru_cache

from services.embeddings import EMBEDDING_MODEL_NAME, get_chroma_collection, get_embedding_model
from core.db import get_db_connection
from core.config import RERANKER_MODEL_NAME

# ── Cross-encoder reranker ─────────────────────────────────────────────────────
# Model: cross-encoder/ms-marco-MiniLM-L-6-v2  (~85 MB, downloads on first use)
#
# A cross-encoder scores (query, passage) pairs jointly by concatenating both
# into a single BERT forward pass.  Far more accurate than cosine similarity
# (bi-encoder) but too slow for full-corpus retrieval — so we use it only as
# a reranking step over the top-15 RRF candidates.
#
# Retrieve (fast, approximate) → Rerank (accurate, exact) is the canonical
# two-stage retrieval architecture used by:
#   • Azure Cognitive Search Semantic Ranker
#   • Cohere Rerank API
#   • Amazon Kendra Smart Ranking
#   • Google Vertex AI Ranking API
#
# ms-marco-MiniLM-L-6-v2 benchmarks:
#   MRR@10 = 39.0 on MS MARCO Passage (vs 40.1 for L-12 at 3× slower).
#   ~3 ms per (query, passage) pair on CPU — negligible for 15 candidates.
_CE_MODEL_NAME = RERANKER_MODEL_NAME
_cross_encoder = None   # None = not yet loaded; False = load failed (no retry)


def _get_cross_encoder():
    """Return the shared cross-encoder, loading it lazily on first search."""
    global _cross_encoder
    if _cross_encoder is None:
        try:
            from sentence_transformers import CrossEncoder
            import torch
            if torch.cuda.is_available():
                device = "cuda"
            elif getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
                device = "mps"          # Apple Silicon GPU — much faster than CPU
            else:
                device = "cpu"
            # 256 tokens is plenty for chunk-sized passages and ~2x faster than 512
            _cross_encoder = CrossEncoder(_CE_MODEL_NAME, max_length=256, device=device)
            print(f"Cross-encoder loaded on {device.upper()}.")
        except Exception as e:
            print(f"Cross-encoder load failed ({e}) — reranking disabled.")
            _cross_encoder = False
    return _cross_encoder if _cross_encoder is not False else None


# ── English stopword list ──────────────────────────────────────────────────────
# Stripped from FTS queries only — semantic queries keep full text for context.
_STOPWORDS: frozenset[str] = frozenset({
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "shall", "can", "this", "that",
    "these", "those", "it", "its", "as", "if", "then", "than", "so",
    "up", "out", "about", "into", "through", "during", "before", "after",
    "above", "below", "what", "which", "who", "whom", "when", "where",
    "why", "how", "all", "each", "every", "both", "few", "more", "most",
    "other", "some", "such", "no", "not", "only", "same", "too", "very",
    "just", "because", "while", "although", "also", "i", "me", "my",
    "we", "our", "you", "your", "he", "she", "his", "her", "they", "their",
    "them", "us", "any", "many", "much", "own", "there", "here", "now",
    "get", "got", "go", "goes", "went", "come", "came", "take", "make",
    "know", "see", "use", "one", "two", "three", "four", "five", "new",
    "like", "time", "year", "way", "day", "thing", "man", "woman", "child",
    "world", "life", "hand", "part", "place", "case", "week", "company",
    "system", "program", "question", "work", "government", "number", "night",
    "point", "home", "water", "room", "mother", "area", "money", "story",
    "fact", "month", "lot", "right", "study", "book", "eye", "job", "word",
    "business", "issue", "side", "kind", "head", "house", "service", "friend",
    "father", "power", "hour", "game", "line", "end", "among", "never",
    "last", "long", "great", "little", "own", "old", "high", "big", "small",
    "large", "next", "early", "young", "important", "public", "private", "real",
    "best", "free", "used", "find", "give", "tell", "call", "keep", "let",
    "begin", "show", "hear", "play", "run", "move", "live", "believe", "hold",
    "bring", "happen", "write", "provide", "sit", "stand", "lose", "pay",
    "meet", "include", "continue", "set", "learn", "change", "lead", "understand",
    "watch", "follow", "stop", "create", "speak", "read", "spend", "grow",
    "open", "walk", "win", "offer", "remember", "love", "consider", "appear",
    "buy", "wait", "serve", "die", "send", "expect", "build", "stay", "fall",
    "cut", "reach", "kill", "remain", "suggest", "raise", "pass", "sell",
    "require", "report", "decide", "pull",
})

# ── Weighted RRF constants ─────────────────────────────────────────────────────
# Benchmark result: BM25 outperforms semantic on identifier-heavy corpora
# (course codes, names, exact terms). Default weights give BM25 3× influence.
# Override via env vars without code changes:
#   export RRF_KW_WEIGHT=1.0 RRF_SEM_WEIGHT=1.0  ← symmetric (original behaviour)
#   export RRF_KW_WEIGHT=2.0 RRF_SEM_WEIGHT=0.5  ← more aggressive BM25 boost
RRF_K          = 60
RRF_KW_WEIGHT  = float(os.getenv("RRF_KW_WEIGHT",  "2.0"))
RRF_SEM_WEIGHT = float(os.getenv("RRF_SEM_WEIGHT", "1.0"))


def get_documents_metadata_batch(doc_ids: list[str]) -> dict[str, dict]:
    """Fetch metadata for multiple doc_ids in one SQL query."""
    if not doc_ids:
        return {}
    placeholders = ",".join("?" * len(doc_ids))
    conn = get_db_connection()
    rows = conn.execute(
        f"SELECT id, filename, summary, tags, key_findings, entities "
        f"FROM documents WHERE id IN ({placeholders})",
        doc_ids,
    ).fetchall()
    conn.close()
    return {
        row["id"]: {
            "filename": row["filename"],
            "summary": row["summary"],
            "tags": json.loads(row["tags"]) if row["tags"] else [],
            "key_findings": json.loads(row["key_findings"]) if row["key_findings"] else [],
            "entities": json.loads(row["entities"]) if row["entities"] else {},
        }
        for row in rows
    }


def _expand_query_terms(query_text: str) -> list[str]:
    """
    YAKE-based query expansion.

    For short queries (1-3 words) this is a no-op — YAKE adds nothing useful.
    For longer natural-language queries (>= 4 words) YAKE extracts the most
    statistically salient unigrams and bigrams, which are added as additional
    OR terms to the BM25 query.

    Example: "courses about neural network architectures for image recognition"
      raw terms:  ["courses", "neural", "network", "architectures", "image", "recognition"]
      YAKE adds:  ["neural network", "image recognition"]
      Final FTS:  "courses OR neural OR network OR architectures OR image OR recognition
                   OR neural network OR image recognition"

    Industry reference: Elasticsearch's Multi-Match + query-time boosting,
    Solr's eDisMax QueryParser, and Azure Cognitive Search all perform query
    term expansion as a first-pass enrichment step.
    """
    words = [w for w in re.findall(r"\w+", query_text.lower()) if len(w) > 1]
    if len(words) < 4:
        return []  # short query — expansion adds noise, not signal
    try:
        import yake
        kw = yake.KeywordExtractor(lan="en", n=2, dedupLim=0.7, top=4)
        phrases = [p for p, _ in kw.extract_keywords(query_text)]
        # Only keep phrases that aren't just one of the original tokens
        expanded = [p for p in phrases if " " in p or p.lower() not in {w.lower() for w in words}]
        return expanded[:3]
    except Exception:
        return []


def _fts_keyword_ranks(query_text: str) -> dict[str, int]:
    """
    Returns {doc_id: rank} for BM25-ranked FTS5 results (1-indexed, lower = better).

    Stopwords are stripped so common words like "is / the / a" don't dilute BM25.
    For longer queries, YAKE-based query expansion adds salient bigrams as
    additional OR terms, improving recall for multi-word concepts.
    """
    raw_terms = re.findall(r"\w+", query_text.lower())
    terms = [t for t in raw_terms if len(t) > 1 and t not in _STOPWORDS]
    if not terms:
        # All terms were stopwords — fall back to unfiltered (so we still return something)
        terms = [t for t in raw_terms if len(t) > 1]
    if not terms:
        return {}

    # Query expansion: add YAKE bigrams for long natural-language queries
    expanded = _expand_query_terms(query_text)
    all_terms = terms + [f'"{p}"' for p in expanded]  # phrase queries in double-quotes

    fts_query = " OR ".join(all_terms)
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        rows = cursor.execute(
            "SELECT id FROM documents_fts WHERE text MATCH ? ORDER BY bm25(documents_fts) LIMIT 50",
            (fts_query,),
        ).fetchall()
        return {r["id"]: rank + 1 for rank, r in enumerate(rows)}
    except Exception as exc:
        print(f"FTS5 error for '{fts_query}': {exc}")
        return {}
    finally:
        conn.close()


@lru_cache(maxsize=512)
def _encode_query_cached(query_text: str) -> list:
    """LRU-cached query embedding — identical queries skip re-encoding."""
    model = get_embedding_model()
    query_for_embed = query_text
    return model.encode(query_for_embed).tolist()


def hybrid_search(query_text: str, limit: int = 5) -> list[dict]:
    """
    Hybrid search: vector similarity (ChromaDB) + BM25 keyword (SQLite FTS5),
    fused via Weighted Reciprocal Rank Fusion.

    score = RRF_KW_WEIGHT/(k + keyword_rank) + RRF_SEM_WEIGHT/(k + semantic_rank)

    Default weights (1.5 / 0.5) give BM25 3× more influence than semantic.
    Tuned from benchmark: BM25 achieves 92% R@1 vs 64% semantic on this corpus.
    Both weights are overridable via RRF_KW_WEIGHT / RRF_SEM_WEIGHT env vars.
    """
    collection = get_chroma_collection()
    total_chunks = collection.count()
    if total_chunks == 0:
        return []

    # --- 1. Keyword ranks (FTS5 BM25) ---
    keyword_ranks = _fts_keyword_ranks(query_text)
    kw_penalty = len(keyword_ranks) + RRF_K

    # --- 2. Semantic search (ChromaDB) — cached embedding ---
    n_results = min(100, total_chunks)
    vector_results = collection.query(
        query_embeddings=[_encode_query_cached(query_text)],
        n_results=n_results,
    )

    if not vector_results or not vector_results["ids"] or not vector_results["ids"][0]:
        return []

    collection_space = (collection.metadata or {}).get("hnsw:space", "l2")

    # --- 3. Build chunks with RRF scores ---
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
        rrf_score = (RRF_KW_WEIGHT / (RRF_K + kw_rank) +
                     RRF_SEM_WEIGHT / (RRF_K + sem_rank))
        cos_sim = (max(0.0, 1.0 - distance) if collection_space == "cosine"
                   else max(0.0, 1.0 - distance**2 / 2.0))
        chunks.append({
            "chunk_id": chunk_id,
            "document_id": doc_id,
            "page": meta["page"],
            "text": text,
            "score": round(rrf_score, 6),
            "similarity": round(cos_sim, 4),
        })

    # --- 4. Sort, deduplicate, then batch-fetch all metadata in ONE query ---
    # Rerank only a tight candidate pool — reranking 50 pairs on CPU/MPS is the
    # dominant cost. limit*3 (min 15) keeps recall while cutting latency sharply.
    rerank_pool = min(max(limit * 3, 15), 30)
    chunks.sort(key=lambda x: x["score"], reverse=True)

    seen_chunks: set[str] = set()
    top_chunks: list[dict] = []
    for chunk in chunks:
        if chunk["chunk_id"] in seen_chunks:
            continue
        seen_chunks.add(chunk["chunk_id"])
        top_chunks.append(chunk)
        if len(top_chunks) >= rerank_pool:
            break

    unique_doc_ids = list(dict.fromkeys(c["document_id"] for c in top_chunks))
    metadata_map = get_documents_metadata_batch(unique_doc_ids)

    results: list[dict] = []
    for chunk in top_chunks:
        doc_meta = metadata_map.get(chunk["document_id"])
        if not doc_meta:
            continue
        chunk.update(doc_meta)
        results.append(chunk)

    # --- 5. Cross-encoder reranking on GPU ---
    ce_model = _get_cross_encoder()
    if ce_model and len(results) > 1:
        try:
            pairs = [(query_text, r["text"]) for r in results]
            ce_scores = ce_model.predict(pairs, show_progress_bar=False)
            for r, ce_score in zip(results, ce_scores):
                r["ce_score"] = round(float(ce_score), 4)
            results.sort(key=lambda x: x.get("ce_score", 0.0), reverse=True)
        except Exception as ce_err:
            print(f"Cross-encoder reranking skipped: {ce_err}")

    return results[:limit]
