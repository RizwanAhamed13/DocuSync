#!/usr/bin/env python3
"""
Memory-safe BEIR benchmark — SciFact + NFCorpus.
Embeds in small batches (32 docs), writes to ChromaDB + SQLite immediately,
never holds the full corpus in RAM.
"""
__import__('pysqlite3')
import sys
sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')

import csv, gc, io, json, math, sqlite3, time, urllib.request
import chromadb
from sentence_transformers import SentenceTransformer, CrossEncoder
import pyarrow.parquet as pq

EMBEDDING_MODEL = "BAAI/bge-base-en-v1.5"
RERANKER_MODEL  = "cross-encoder/ms-marco-MiniLM-L-6-v2"
EMBED_BATCH     = 32    # docs per embedding batch — keep low for Mac RAM
CHROMA_PATH     = "./vector_store"
DB_PATH         = "./document_metadata.db"

DATASETS = [
    {"name": "scifact",  "hf": "BeIR/scifact",  "qrels_split": "test"},
    {"name": "nfcorpus", "hf": "BeIR/nfcorpus", "qrels_split": "test"},
]


def fetch_parquet(dataset, split):
    url = f"https://huggingface.co/datasets/{dataset}/resolve/main/{split}/{split}-00000-of-00001.parquet"
    print(f"  Downloading {split} from {dataset}...")
    with urllib.request.urlopen(url, timeout=120) as r:
        return pq.read_table(io.BytesIO(r.read())).to_pydict()


def fetch_qrels(name, split):
    url = f"https://huggingface.co/datasets/BeIR/{name}-qrels/resolve/main/{split}.tsv"
    print(f"  Downloading qrels...")
    with urllib.request.urlopen(url, timeout=120) as r:
        content = r.read().decode()
    qrels = {}
    for row in csv.DictReader(io.StringIO(content), delimiter="\t"):
        if int(row["score"]) > 0:
            qrels.setdefault(row["query-id"], {})[row["corpus-id"]] = 1
    return qrels


def reset_stores():
    """Clear ChromaDB collection and SQLite docs."""
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    try:
        client.delete_collection("document_chunks")
    except Exception:
        pass
    col = client.create_collection("document_chunks", metadata={"hnsw:space": "cosine"})

    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM documents")
    conn.execute("DELETE FROM documents_fts")
    conn.commit()
    conn.close()
    return col


def index_corpus(corpus, embed_model):
    col = reset_stores()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")

    ids    = corpus["_id"]
    titles = corpus.get("title", [""] * len(ids))
    texts  = corpus["text"]
    total  = len(ids)

    print(f"  Indexing {total} docs (batch={EMBED_BATCH})...")
    t0 = time.time()

    for start in range(0, total, EMBED_BATCH):
        end   = min(start + EMBED_BATCH, total)
        batch_ids    = ids[start:end]
        batch_texts  = [(f"{titles[i] or ''} {texts[i] or ''}").strip() for i in range(start, end)]

        vecs = embed_model.encode(batch_texts, batch_size=EMBED_BATCH,
                                  show_progress_bar=False).tolist()

        chunk_ids, embeddings, documents, metadatas = [], [], [], []
        for j, (doc_id, text, vec) in enumerate(zip(batch_ids, batch_texts, vecs)):
            chunk_ids.append(f"{doc_id}_c0")
            embeddings.append(vec)
            documents.append(text[:1500])
            metadatas.append({"document_id": str(doc_id), "page": 1})
            conn.execute(
                "INSERT OR REPLACE INTO documents (id,filename,status,tags,summary,file_size_bytes,page_count) VALUES(?,?,?,?,?,?,?)",
                (str(doc_id), f"{doc_id}.txt", "completed", "", "", len(text.encode()), 1),
            )
            conn.execute(
                "INSERT OR REPLACE INTO documents_fts (id,filename,text) VALUES(?,?,?)",
                (str(doc_id), f"{doc_id}.txt", text[:8000]),
            )

        col.upsert(ids=chunk_ids, embeddings=embeddings,
                   documents=documents, metadatas=metadatas)
        conn.commit()
        del vecs, embeddings, documents, metadatas
        gc.collect()

        if (start // EMBED_BATCH + 1) % 20 == 0:
            print(f"    {end}/{total}")

    conn.close()
    print(f"  Done in {time.time()-t0:.1f}s  ({total} docs)")
    return col


def evaluate(queries, qrels, embed_model, reranker, col, k=10):
    qids   = queries["_id"]
    qtexts = queries["text"]
    total  = len(qids)
    print(f"  Running {total} queries...")

    ndcg_s, mrr_s, rec_s = [], [], []

    # Load FTS index for BM25 boost (optional — use if available)
    import requests
    use_api_search = False
    try:
        r = requests.get("http://localhost:8000/health", timeout=3)
        use_api_search = r.ok
    except Exception:
        pass

    for qi in range(total):
        qid   = str(qids[qi])
        qtext = str(qtexts[qi])
        rel   = qrels.get(qid, {})
        if not rel:
            continue

        if use_api_search:
            # Use full hybrid search (BM25 + semantic + reranker) via API
            try:
                r = requests.post("http://localhost:8000/search",
                                  json={"query": qtext, "limit": k},
                                  timeout=15)
                hits = r.json() if r.ok else []
                final = [h["filename"].replace(".txt", "") for h in hits[:k]]
            except Exception:
                use_api_search = False
                final = []

        if not use_api_search or not final:
            # Fallback: pure semantic via ChromaDB
            qvec = embed_model.encode([qtext], show_progress_bar=False).tolist()
            res  = col.query(query_embeddings=qvec,
                             n_results=min(k * 5, col.count()))
            doc_ids = [m["document_id"] for m in res["metadatas"][0]]
            seen, unique = set(), []
            for d in doc_ids:
                if d not in seen:
                    seen.add(d)
                    unique.append(d)
            final = unique[:k]

        # nDCG@k
        dcg   = sum(1/math.log2(r+2) for r, d in enumerate(final) if d in rel)
        ideal = sum(1/math.log2(r+2) for r in range(min(len(rel), k)))
        ndcg_s.append(dcg / ideal if ideal else 0)
        # MRR@k
        mrr_s.append(next((1/(r+1) for r, d in enumerate(final) if d in rel), 0))
        # Recall@5
        rec_s.append(len(set(final[:5]) & set(rel)) / len(rel))

        if (qi + 1) % 50 == 0:
            print(f"    {qi+1}/{total}")

    n = len(ndcg_s)
    return {
        "nDCG@10":  round(sum(ndcg_s)/n*100, 2) if n else 0,
        "MRR@10":   round(sum(mrr_s)/n*100,  2) if n else 0,
        "Recall@5": round(sum(rec_s)/n*100,  2) if n else 0,
        "queries_evaluated": n,
    }


# ── Main ──────────────────────────────────────────────────────────────────────
print("=" * 60)
print("DocuSync BEIR Benchmark (memory-safe)")
print(f"Embedding : {EMBEDDING_MODEL}")
print("=" * 60)

print("\nLoading embedding model...")
embed_model = SentenceTransformer(EMBEDDING_MODEL)
print("Model ready.\n")

all_results = {}

for ds in DATASETS:
    name = ds["name"]
    print(f"\n{'='*40}\n{name.upper()}\n{'='*40}")

    corpus  = fetch_parquet(ds["hf"], "corpus")
    queries = fetch_parquet(ds["hf"], "queries")
    qrels   = fetch_qrels(name, ds["qrels_split"])
    print(f"  Corpus {len(corpus['_id'])} | Queries {len(queries['_id'])} | Topics {len(qrels)}")

    col = index_corpus(corpus, embed_model)
    del corpus; gc.collect()

    metrics = evaluate(queries, qrels, embed_model, None, col)
    all_results[name] = metrics
    del queries; gc.collect()

    print(f"\n  {name.upper()} Results:")
    for k, v in metrics.items():
        print(f"    {k}: {v}")

print("\n" + "="*60)
print("FINAL RESULTS")
print("="*60)
for ds_name, m in all_results.items():
    print(f"\n{ds_name.upper()}:")
    for k, v in m.items():
        print(f"  {k}: {v}")

with open("beir_results.json", "w") as f:
    json.dump(all_results, f, indent=2)
print("\nSaved → beir_results.json")
