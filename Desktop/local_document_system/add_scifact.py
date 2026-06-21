#!/usr/bin/env python3
"""Add SciFact corpus (5183 docs) to the existing index without resetting."""
__import__('pysqlite3')
import sys
sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')

import csv, gc, io, sqlite3, time, urllib.request
import chromadb
from sentence_transformers import SentenceTransformer
import pyarrow.parquet as pq

EMBEDDING_MODEL = "BAAI/bge-base-en-v1.5"
EMBED_BATCH     = 32
CHROMA_PATH     = "./vector_store"
DB_PATH         = "./document_metadata.db"

def fetch_parquet(dataset, split):
    url = f"https://huggingface.co/datasets/{dataset}/resolve/main/{split}/{split}-00000-of-00001.parquet"
    print(f"  Downloading {split}...")
    with urllib.request.urlopen(url, timeout=120) as r:
        return pq.read_table(io.BytesIO(r.read())).to_pydict()

print("Loading embedding model...")
embed_model = SentenceTransformer(EMBEDDING_MODEL)

print("Fetching SciFact corpus...")
corpus = fetch_parquet("BeIR/scifact", "corpus")

ids    = corpus["_id"]
titles = corpus.get("title", [""] * len(ids))
texts  = corpus["text"]
total  = len(ids)
print(f"  {total} docs to add")

# Connect to existing stores (no reset)
client = chromadb.PersistentClient(path=CHROMA_PATH)
col = client.get_or_create_collection("document_chunks", metadata={"hnsw:space": "cosine"})
conn = sqlite3.connect(DB_PATH)
conn.execute("PRAGMA journal_mode=WAL")

print(f"  Current DB: {col.count()} chunks already indexed")
print(f"  Indexing SciFact in batches of {EMBED_BATCH}...")
t0 = time.time()

for start in range(0, total, EMBED_BATCH):
    end = min(start + EMBED_BATCH, total)
    batch_ids   = ids[start:end]
    batch_texts = [(f"{titles[i] or ''} {texts[i] or ''}").strip() for i in range(start, end)]

    vecs = embed_model.encode(batch_texts, batch_size=EMBED_BATCH, show_progress_bar=False).tolist()

    chunk_ids, embeddings, documents, metadatas = [], [], [], []
    for doc_id, text, vec in zip(batch_ids, batch_texts, vecs):
        chunk_ids.append(f"{doc_id}_c0")
        embeddings.append(vec)
        documents.append(text[:1500])
        metadatas.append({"document_id": str(doc_id), "page": 1})
        conn.execute(
            "INSERT OR REPLACE INTO documents (id,filename,status,tags,summary,file_size_bytes,page_count) VALUES(?,?,?,?,?,?,?)",
            (str(doc_id), f"{doc_id}.txt", "completed", "Science,Research", "SciFact scientific claim document.", len(text.encode()), 1),
        )
        conn.execute(
            "INSERT OR REPLACE INTO documents_fts (id,filename,text) VALUES(?,?,?)",
            (str(doc_id), f"{doc_id}.txt", text[:8000]),
        )

    col.upsert(ids=chunk_ids, embeddings=embeddings, documents=documents, metadatas=metadatas)
    conn.commit()
    del vecs, embeddings, documents, metadatas
    gc.collect()

    if (start // EMBED_BATCH + 1) % 20 == 0:
        print(f"    {end}/{total}")

conn.close()
elapsed = time.time() - t0
print(f"\nDone! Added {total} SciFact docs in {elapsed:.1f}s")
print(f"Total chunks in vector store: {col.count()}")
