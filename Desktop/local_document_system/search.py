import json
import os
import re
import sqlite3

from embeddings import EMBEDDING_MODEL_NAME, get_chroma_collection, get_embedding_model
from indexer import get_db_connection

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
_CE_MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"
_cross_encoder = None   # None = not yet loaded; False = load failed (no retry)


def _get_cross_encoder():
    """Return the shared cross-encoder, loading it lazily on first search."""
    global _cross_encoder
    if _cross_encoder is None:
        try:
            from sentence_transformers import CrossEncoder
            _cross_encoder = CrossEncoder(_CE_MODEL_NAME, max_length=512)
        except Exception as e:
            print(f"Cross-encoder load failed ({e}) — reranking disabled.")
            _cross_encoder = False  # sentinel: do not retry on every query
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
RRF_KW_WEIGHT  = float(os.getenv("RRF_KW_WEIGHT",  "1.5"))
RRF_SEM_WEIGHT = float(os.getenv("RRF_SEM_WEIGHT", "0.5"))


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
    fused via Weighted Reciprocal Rank Fusion.

    score = RRF_KW_WEIGHT/(k + keyword_rank) + RRF_SEM_WEIGHT/(k + semantic_rank)

    Default weights (1.5 / 0.5) give BM25 3× more influence than semantic.
    Tuned from benchmark: BM25 achieves 92% R@1 vs 64% semantic on this corpus.
    Both weights are overridable via RRF_KW_WEIGHT / RRF_SEM_WEIGHT env vars.
    """
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
    # BGE models are instruction-tuned: queries need this prefix for best retrieval.
    # Passage embeddings (stored at index time) are encoded without the prefix.
    query_for_embed = (
        f"Represent this sentence for searching relevant passages: {query_text}"
        if "bge" in EMBEDDING_MODEL_NAME.lower()
        else query_text
    )
    vector_results = collection.query(
        query_embeddings=[model.encode(query_for_embed).tolist()],
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

        rrf_score = (RRF_KW_WEIGHT  / (RRF_K + kw_rank) +
                     RRF_SEM_WEIGHT / (RRF_K + sem_rank))

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
    # Collect up to 3× limit (min 15) candidates so the cross-encoder has
    # enough material to rerank.  We trim to `limit` after reranking.
    rerank_pool = max(limit * 3, 15)
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

        if len(results) >= rerank_pool:
            break

    # --- 5. Cross-encoder reranking (ms-marco-MiniLM-L-6-v2) ---
    # Score each (query, passage) pair jointly — much more accurate than
    # cosine similarity for distinguishing closely-ranked candidates.
    # Skipped gracefully if the model failed to load or results are empty.
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
            # Fall back to RRF ordering — results already sorted correctly

    return results[:limit]
