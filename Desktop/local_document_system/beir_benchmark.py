#!/usr/bin/env python3
"""BEIR benchmark — SciFact + NFCorpus — against DocuSync hybrid search."""
import csv, io, json, math, time, urllib.request
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
import pyarrow.parquet as pq

API = "http://127.0.0.1:8000"
DATASETS = [
    {"name": "scifact",  "hf": "BeIR/scifact",  "qrels_split": "test"},
    {"name": "nfcorpus", "hf": "BeIR/nfcorpus", "qrels_split": "test"},
]


def _hf_parquet(dataset, split):
    url = f"https://huggingface.co/datasets/{dataset}/resolve/main/{split}/{split}-00000-of-00001.parquet"
    print(f"  Fetching {url}")
    with urllib.request.urlopen(url, timeout=120) as r:
        return pq.read_table(io.BytesIO(r.read())).to_pydict()


def _hf_tsv_qrels(dataset_name, split):
    """Fetch TSV qrels from BeIR/<name>-qrels repo."""
    url = f"https://huggingface.co/datasets/BeIR/{dataset_name}-qrels/resolve/main/{split}.tsv"
    print(f"  Fetching qrels {url}")
    with urllib.request.urlopen(url, timeout=120) as r:
        content = r.read().decode("utf-8")
    reader = csv.DictReader(io.StringIO(content), delimiter="\t")
    qrels = {}
    for row in reader:
        qid = row["query-id"]
        did = row["corpus-id"]
        score = int(row["score"])
        if score > 0:
            qrels.setdefault(qid, {})[did] = score
    return qrels


def upload_corpus(rows, label):
    ids = rows["_id"]
    titles = rows.get("title", [""] * len(ids))
    texts = rows["text"]
    print(f"  Uploading {len(ids)} docs ({label})...")
    ok = fail = 0

    def _up(i):
        body = ((titles[i] or "") + " " + (texts[i] or "")).strip()
        fname = f"{ids[i]}.txt"
        r = requests.post(
            f"{API}/upload",
            files={"file": (fname, body.encode(), "text/plain")},
            timeout=30,
        )
        return r.status_code == 200

    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(_up, i): i for i in range(len(ids))}
        for n, f in enumerate(as_completed(futs), 1):
            if f.result():
                ok += 1
            else:
                fail += 1
            if n % 500 == 0:
                print(f"    {n}/{len(ids)}")
    print(f"  Uploaded {ok} ok, {fail} failed")


def wait_indexed(target):
    print("  Waiting for indexing...")
    while True:
        r = requests.get(f"{API}/health", timeout=10).json()
        idx = r["documents"]["indexed"]
        proc = r["documents"]["processing"]
        print(f"    indexed={idx} processing={proc}")
        if idx >= target and proc == 0:
            break
        time.sleep(10)


def run_queries(queries, qrels, label, k=10):
    print(f"  Running {len(queries['_id'])} queries...")
    qids = queries["_id"]
    qtexts = queries["text"]

    ndcg_scores, mrr_scores, recall_scores = [], [], []

    def _query(i):
        qid = str(qids[i])
        text = qtexts[i]
        r = requests.post(f"{API}/search", json={"query": text, "limit": k}, timeout=30)
        if r.status_code != 200:
            return qid, []
        hits = r.json()
        if isinstance(hits, dict):
            hits = hits.get("results", [])
        # strip .txt extension from returned filenames
        doc_ids = [h["filename"].replace(".txt", "") for h in hits]
        return qid, doc_ids

    results = {}
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(_query, i): i for i in range(len(qids))}
        for n, f in enumerate(as_completed(futs), 1):
            qid, doc_ids = f.result()
            results[qid] = doc_ids
            if n % 50 == 0:
                print(f"    {n}/{len(qids)} queries done")

    # Compute metrics
    for qid, doc_ids in results.items():
        rel = qrels.get(qid, {})
        if not rel:
            continue

        # nDCG@10
        dcg = sum(
            (1 / math.log2(r + 2)) for r, d in enumerate(doc_ids) if d in rel
        )
        ideal = sum(1 / math.log2(r + 2) for r in range(min(len(rel), k)))
        ndcg_scores.append(dcg / ideal if ideal > 0 else 0)

        # MRR@10
        mrr = next(
            (1 / (r + 1) for r, d in enumerate(doc_ids) if d in rel), 0
        )
        mrr_scores.append(mrr)

        # Recall@5
        top5 = set(doc_ids[:5])
        recall_scores.append(len(top5 & set(rel)) / len(rel))

    return {
        "nDCG@10": round(sum(ndcg_scores) / len(ndcg_scores) * 100, 2) if ndcg_scores else 0,
        "MRR@10":  round(sum(mrr_scores)  / len(mrr_scores)  * 100, 2) if mrr_scores else 0,
        "Recall@5": round(sum(recall_scores) / len(recall_scores) * 100, 2) if recall_scores else 0,
        "queries_evaluated": len(ndcg_scores),
    }


print("=" * 60)
print("DocuSync BEIR Benchmark — New Model Stack")
print("BGE-large-en-v1.5 + GTE-Reranker-ModernBERT + DistilBART + DeBERTa")
print("=" * 60)

all_results = {}

for ds in DATASETS:
    name = ds["name"]
    hf = ds["hf"]
    qrels_split = ds["qrels_split"]

    print(f"\n{'=' * 40}")
    print(f"Dataset: {name.upper()}")
    print("=" * 40)

    print("  Resetting system...")
    requests.post(f"{API}/reset", timeout=30)
    time.sleep(2)

    corpus = _hf_parquet(hf, "corpus")
    upload_corpus(corpus, name)
    wait_indexed(len(corpus["_id"]))

    queries = _hf_parquet(hf, "queries")
    qrels = _hf_tsv_qrels(name, qrels_split)
    print(f"  Queries: {len(queries['_id'])}, Qrel topics: {len(qrels)}")

    metrics = run_queries(queries, qrels, name)
    all_results[name] = metrics

    print(f"\n  --- {name.upper()} Results ---")
    for k, v in metrics.items():
        print(f"    {k}: {v}")

print("\n" + "=" * 60)
print("FINAL RESULTS")
print("=" * 60)
for ds_name, metrics in all_results.items():
    print(f"\n{ds_name.upper()}:")
    for k, v in metrics.items():
        print(f"  {k}: {v}")

with open("/root/beir_results.json", "w") as f:
    json.dump(all_results, f, indent=2)
print("\nResults saved to /root/beir_results.json")
