import json
import logging
import os
import re
import sqlite3

from embeddings import EMBEDDING_MODEL_NAME, get_chroma_collection, get_embedding_model
from indexer import get_db_connection

logger = logging.getLogger(__name__)

# ── Cross-encoder reranker ─────────────────────────────────────────────────────
# BAAI/bge-reranker-large (560M params, GPU)
# Scores (query, passage) pairs jointly — far more accurate than cosine similarity.
# Used only as a reranking step over the top-N RRF candidates (two-stage retrieval).
_CE_MODEL_NAME = "BAAI/bge-reranker-large"
_cross_encoder = None   # None = not yet loaded; False = load failed (no retry)


def _get_cross_encoder():
    """Return the shared cross-encoder, loading it lazily on first search."""
    global _cross_encoder
    if _cross_encoder is None:
        try:
            from sentence_transformers import CrossEncoder
            _cross_encoder = CrossEncoder(_CE_MODEL_NAME, max_length=512)
        except Exception as e:
            logger.warning(f"Cross-encoder load failed ({e}) — reranking disabled.")
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
RRF_KW_WEIGHT  = float(os.getenv("RRF_KW_WEIGHT",  "0.6"))
RRF_SEM_WEIGHT = float(os.getenv("RRF_SEM_WEIGHT", "0.4"))


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


def _adaptive_rrf_weights(query_text: str) -> tuple[float, float]:
    """
    Dynamically choose RRF weights based on query type.

    Keyword query (short, contains exact terms, course codes, dates):
      BM25 heavy — 0.8 / 0.2.  These queries have exact token matches and BM25
      will nail them; semantic adds noise from paraphrase matches.

    Semantic query (long natural-language question, ≥6 words, no code patterns):
      Balanced — 0.5 / 0.5.  Semantic embedding captures meaning across
      paraphrases; BM25 alone misses synonyms.

    Mixed (default): env-var defaults (0.6 / 0.4).
    """
    # Respect explicit env-var overrides
    if os.getenv("RRF_KW_WEIGHT") or os.getenv("RRF_SEM_WEIGHT"):
        return RRF_KW_WEIGHT, RRF_SEM_WEIGHT

    words = query_text.strip().split()
    # Signals of a keyword / exact-match query
    has_course_code = bool(re.search(r"\b[A-Z]{2,6}\s*\d{3,4}\b", query_text))
    has_date = bool(re.search(r"\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b|\b20\d{2}\b", query_text))
    is_short = len(words) <= 4

    if has_course_code or has_date or is_short:
        return 0.8, 0.2   # keyword-heavy

    is_long_question = len(words) >= 8 and "?" in query_text
    if is_long_question:
        return 0.5, 0.5   # balanced semantic

    return RRF_KW_WEIGHT, RRF_SEM_WEIGHT  # default


def hybrid_search(query_text: str, limit: int = 10) -> list[dict]:
    """
    Hybrid search: ChromaDB dense vectors + SQLite FTS5 BM25, fused via
    Adaptive Weighted RRF. Weights shift per query type (see _adaptive_rrf_weights).
    Pipeline: FTS5 → dense embed → RRF → diversity cap → cross-encoder rerank → window expand.
    """
    kw_w, sem_w = _adaptive_rrf_weights(query_text)

    # --- 1. Keyword ranks (FTS5 BM25) ---
    keyword_ranks = _fts_keyword_ranks(query_text)
    # Penalty rank for docs not found by keyword search
    kw_penalty = len(keyword_ranks) + RRF_K
    logger.debug(f"Query '{query_text[:40]}' → adaptive RRF kw={kw_w:.1f} sem={sem_w:.1f}")

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

        rrf_score = (kw_w  / (RRF_K + kw_rank) +
                     sem_w / (RRF_K + sem_rank))

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

    # --- 5. Cross-encoder reranking (bge-reranker-large) ---
    # Score each (query, passage) pair jointly via BAAI/bge-reranker-large.
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
            logger.warning(f"Cross-encoder reranking skipped: {ce_err}")

    # --- 6. Cross-document diversity: max 3 chunks per document ---
    # Prevents all top results coming from the same large document.
    # After reranking, greedily pick results respecting the per-doc cap.
    MAX_CHUNKS_PER_DOC = 3
    doc_chunk_count: dict[str, int] = {}
    diverse: list[dict] = []
    overflow: list[dict] = []  # candidates that exceeded per-doc cap
    for r in results:
        doc_id = r["document_id"]
        if doc_chunk_count.get(doc_id, 0) < MAX_CHUNKS_PER_DOC:
            doc_chunk_count[doc_id] = doc_chunk_count.get(doc_id, 0) + 1
            diverse.append(r)
        else:
            overflow.append(r)
        if len(diverse) >= limit:
            break
    # Fill remaining slots from overflow if we didn't reach limit via diversity
    if len(diverse) < limit:
        diverse.extend(overflow[: limit - len(diverse)])

    # --- 7. Sentence-window context expansion ---
    # For each matched chunk, fetch the adjacent chunks (±1) from ChromaDB and
    # attach them as `context` — a wider window that gives the LLM surrounding
    # sentences without changing what was actually matched (text stays the chunk).
    collection = get_chroma_collection()
    for r in diverse:
        chunk_id: str = r["chunk_id"]
        # Chunk IDs are "{doc_id}_chunk_{n}" — parse the index
        m = re.match(r"^(.+)_chunk_(\d+)$", chunk_id)
        if not m:
            r["context"] = r["text"]
            continue
        doc_id, idx = m.group(1), int(m.group(2))
        neighbor_ids = []
        if idx > 0:
            neighbor_ids.append(f"{doc_id}_chunk_{idx - 1}")
        neighbor_ids.append(chunk_id)
        if True:  # always try next chunk
            neighbor_ids.append(f"{doc_id}_chunk_{idx + 1}")
        try:
            fetched = collection.get(ids=neighbor_ids, include=["documents"])
            id_to_text = dict(zip(fetched["ids"], fetched["documents"]))
            window_parts = [id_to_text[nid] for nid in neighbor_ids if nid in id_to_text]
            r["context"] = " ".join(window_parts)
        except Exception:
            r["context"] = r["text"]

    return diverse
