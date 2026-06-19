"""
DocuSync Standard Benchmark Runner
===================================
Measures retrieval quality and latency against the 30-query QA dataset.

Usage:
    # Server must be running on localhost:8000 first:
    python -m uvicorn main:app --host 0.0.0.0 --port 8000

    # Full run (ingests docs, runs queries, saves report):
    python benchmark/run_benchmark.py

    # Skip re-ingestion if docs already uploaded:
    python benchmark/run_benchmark.py --no-ingest

    # Compare two runs:
    python benchmark/run_benchmark.py --compare results_v1.json results_v2.json

Metrics reported:
    R@1   — fraction of queries where the correct doc appears at rank 1
    R@3   — fraction where correct doc appears in top 3
    R@5   — fraction where correct doc appears in top 5
    MRR@10 — Mean Reciprocal Rank (1/rank of first correct result), up to rank 10
    Mean latency — wall-clock time per query (ms)
    Per-category breakdown — same metrics split by query category
"""

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path

try:
    import httpx
except ImportError:
    sys.exit("Run: pip install httpx")

BENCHMARK_DIR = Path(__file__).parent
DATASET_PATH  = BENCHMARK_DIR / "data" / "qa_dataset.json"
BASE_URL      = os.getenv("DOCUSYNC_URL", "http://localhost:8000")


def load_dataset() -> dict:
    with open(DATASET_PATH) as f:
        return json.load(f)


def wait_for_server(timeout: int = 30) -> bool:
    print(f"Waiting for server at {BASE_URL}…", end="", flush=True)
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = httpx.get(f"{BASE_URL}/health", timeout=2.0)
            if r.status_code == 200:
                print(" ready.")
                return True
        except Exception:
            pass
        time.sleep(1)
        print(".", end="", flush=True)
    print(" TIMEOUT.")
    return False


def ingest_documents(dataset: dict, client: httpx.Client) -> dict[str, str]:
    """
    Upload all test documents from the dataset as text files.
    Returns {doc_id: uploaded_doc_id} mapping from server-assigned IDs.
    """
    print(f"\nIngesting {len(dataset['test_documents'])} test documents…")
    doc_id_map: dict[str, str] = {}

    for doc in dataset["test_documents"]:
        content = doc["content"].encode("utf-8")
        filename = doc["filename"]

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        try:
            with open(tmp_path, "rb") as f:
                r = client.post(
                    f"{BASE_URL}/upload",
                    files={"file": (filename, f, "text/plain")},
                    timeout=60.0,
                )
            if r.status_code == 200:
                server_doc_id = r.json()["document_id"]
                doc_id_map[doc["id"]] = server_doc_id
                print(f"  ✓ {filename} → {server_doc_id}")
            else:
                print(f"  ✗ {filename}: HTTP {r.status_code} — {r.text[:100]}")
        finally:
            os.unlink(tmp_path)

    # Wait for all docs to finish processing
    print("Waiting for ingestion to complete…", end="", flush=True)
    deadline = time.time() + 120
    pending = set(doc_id_map.values())
    while pending and time.time() < deadline:
        done = set()
        for srv_id in pending:
            try:
                r = client.get(f"{BASE_URL}/documents/{srv_id}/status", timeout=5.0)
                status = r.json().get("status", "")
                if status in ("completed", "failed"):
                    done.add(srv_id)
            except Exception:
                pass
        pending -= done
        if pending:
            time.sleep(2)
            print(".", end="", flush=True)
    print(f" done. ({len(doc_id_map)} documents indexed)")
    return doc_id_map


def run_query(query: str, client: httpx.Client, limit: int = 10) -> tuple[list[dict], float]:
    """Run a single search query. Returns (results, latency_ms)."""
    t0 = time.perf_counter()
    r = client.post(
        f"{BASE_URL}/search",
        json={"query": query, "limit": limit},
        timeout=30.0,
    )
    latency_ms = (time.perf_counter() - t0) * 1000
    if r.status_code == 200:
        return r.json(), latency_ms
    return [], latency_ms


def reciprocal_rank(results: list[dict], relevant_filenames: set[str]) -> float:
    """Return 1/rank of the first relevant result, or 0 if not found in top 10."""
    for rank, r in enumerate(results[:10], start=1):
        filename = r.get("filename", "")
        if any(rel.lower() in filename.lower() or filename.lower() in rel.lower()
               for rel in relevant_filenames):
            return 1.0 / rank
    return 0.0


def hits_at_k(results: list[dict], relevant_filenames: set[str], k: int) -> bool:
    """Return True if any relevant document appears in top-k results."""
    for r in results[:k]:
        filename = r.get("filename", "")
        if any(rel.lower() in filename.lower() or filename.lower() in rel.lower()
               for rel in relevant_filenames):
            return True
    return False


def evaluate(dataset: dict, doc_id_map: dict[str, str], client: httpx.Client) -> dict:
    """Run all queries and compute metrics."""
    queries = dataset["queries"]
    test_docs = {d["id"]: d["filename"] for d in dataset["test_documents"]}

    results_per_query: list[dict] = []
    category_stats: dict[str, list] = {}

    print(f"\nRunning {len(queries)} queries…\n")

    for q in queries:
        relevant_filenames = {
            test_docs[doc_id]
            for doc_id in q["relevant_doc_ids"]
            if doc_id in test_docs
        }

        search_results, latency_ms = run_query(q["query"], client)

        rr   = reciprocal_rank(search_results, relevant_filenames)
        h1   = hits_at_k(search_results, relevant_filenames, 1)
        h3   = hits_at_k(search_results, relevant_filenames, 3)
        h5   = hits_at_k(search_results, relevant_filenames, 5)

        result_entry = {
            "id":        q["id"],
            "category":  q["category"],
            "query":     q["query"],
            "difficulty": q["difficulty"],
            "R@1":       int(h1),
            "R@3":       int(h3),
            "R@5":       int(h5),
            "RR":        round(rr, 4),
            "latency_ms": round(latency_ms, 1),
            "top_result": search_results[0].get("filename", "—") if search_results else "—",
        }
        results_per_query.append(result_entry)

        status = "✓" if h1 else ("~" if h5 else "✗")
        print(f"  {status} [{q['id']}] {q['query'][:55]:<55} R@1={int(h1)} R@5={int(h5)} RR={rr:.2f} {latency_ms:.0f}ms")

        cat = q["category"]
        if cat not in category_stats:
            category_stats[cat] = []
        category_stats[cat].append(result_entry)

    # Aggregate
    n = len(results_per_query)

    def mean(vals):
        return round(sum(vals) / max(len(vals), 1), 4)

    overall = {
        "n_queries":    n,
        "R@1":          mean([r["R@1"]  for r in results_per_query]),
        "R@3":          mean([r["R@3"]  for r in results_per_query]),
        "R@5":          mean([r["R@5"]  for r in results_per_query]),
        "MRR@10":       mean([r["RR"]   for r in results_per_query]),
        "mean_latency_ms": mean([r["latency_ms"] for r in results_per_query]),
        "p50_latency_ms":  sorted([r["latency_ms"] for r in results_per_query])[n // 2],
        "p95_latency_ms":  sorted([r["latency_ms"] for r in results_per_query])[int(n * 0.95)],
    }

    per_category = {}
    for cat_id, cat_results in category_stats.items():
        per_category[cat_id] = {
            "n":     len(cat_results),
            "R@1":   mean([r["R@1"]  for r in cat_results]),
            "R@3":   mean([r["R@3"]  for r in cat_results]),
            "R@5":   mean([r["R@5"]  for r in cat_results]),
            "MRR@10": mean([r["RR"]  for r in cat_results]),
        }

    per_difficulty = {}
    for diff in ("easy", "medium", "hard"):
        dr = [r for r in results_per_query if r["difficulty"] == diff]
        if dr:
            per_difficulty[diff] = {
                "n":   len(dr),
                "R@1": mean([r["R@1"] for r in dr]),
                "R@5": mean([r["R@5"] for r in dr]),
                "MRR@10": mean([r["RR"] for r in dr]),
            }

    return {
        "overall":        overall,
        "per_category":   per_category,
        "per_difficulty": per_difficulty,
        "queries":        results_per_query,
    }


def print_report(report: dict, label: str = "Results") -> None:
    o = report["overall"]
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    print(f"  Queries evaluated : {o['n_queries']}")
    print(f"  R@1               : {o['R@1']:.1%}")
    print(f"  R@3               : {o['R@3']:.1%}")
    print(f"  R@5               : {o['R@5']:.1%}")
    print(f"  MRR@10            : {o['MRR@10']:.4f}")
    print(f"  Mean latency      : {o['mean_latency_ms']:.0f} ms")
    print(f"  p50 latency       : {o['p50_latency_ms']:.0f} ms")
    print(f"  p95 latency       : {o['p95_latency_ms']:.0f} ms")

    cat_names = {
        "exact":    "Exact Lookup",
        "policy":   "Policy Retrieval",
        "semantic": "Semantic Concept",
        "cross":    "Cross-Document",
        "hard":     "Hard / Paraphrase",
    }
    print(f"\n  {'Category':<22} {'n':>3}  {'R@1':>6}  {'R@5':>6}  {'MRR@10':>8}")
    print(f"  {'-'*52}")
    for cat_id, stats in report["per_category"].items():
        name = cat_names.get(cat_id, cat_id)
        print(f"  {name:<22} {stats['n']:>3}  {stats['R@1']:>6.1%}  {stats['R@5']:>6.1%}  {stats['MRR@10']:>8.4f}")

    print(f"\n  {'Difficulty':<12} {'n':>3}  {'R@1':>6}  {'R@5':>6}  {'MRR@10':>8}")
    print(f"  {'-'*40}")
    for diff, stats in report["per_difficulty"].items():
        print(f"  {diff:<12} {stats['n']:>3}  {stats['R@1']:>6.1%}  {stats['R@5']:>6.1%}  {stats['MRR@10']:>8.4f}")
    print(f"{'='*60}\n")


def print_comparison(report_a: dict, label_a: str, report_b: dict, label_b: str) -> None:
    """Print a side-by-side delta table between two benchmark runs."""
    a, b = report_a["overall"], report_b["overall"]
    print(f"\n{'='*68}")
    print(f"  COMPARISON: {label_a}  vs  {label_b}")
    print(f"{'='*68}")
    metrics = [("R@1", "R@1"), ("R@3", "R@3"), ("R@5", "R@5"), ("MRR@10", "MRR@10"),
               ("Mean latency (ms)", "mean_latency_ms")]
    print(f"  {'Metric':<22} {label_a:>12} {label_b:>12} {'Delta':>10}")
    print(f"  {'-'*58}")
    for label, key in metrics:
        va, vb = a[key], b[key]
        delta = vb - va
        sign  = "+" if delta >= 0 else ""
        if "latency" in key:
            # Lower is better for latency
            arrow = "↓" if delta < 0 else "↑"
            print(f"  {label:<22} {va:>12.1f} {vb:>12.1f} {sign}{delta:>8.1f} {arrow}")
        else:
            arrow = "↑" if delta > 0 else ("↓" if delta < 0 else "→")
            print(f"  {label:<22} {va:>11.1%} {vb:>11.1%} {sign}{delta:>8.1%} {arrow}")
    print(f"{'='*68}\n")


def main():
    parser = argparse.ArgumentParser(description="DocuSync retrieval benchmark")
    parser.add_argument("--no-ingest", action="store_true",
                        help="Skip document ingestion (use already-uploaded docs)")
    parser.add_argument("--output", default="benchmark_results.json",
                        help="Output file for results JSON (default: benchmark_results.json)")
    parser.add_argument("--compare", nargs=2, metavar=("FILE_A", "FILE_B"),
                        help="Compare two saved result JSON files instead of running")
    parser.add_argument("--label", default="DocuSync",
                        help="Label for this run in the report")
    parser.add_argument("--url", default=None,
                        help="Override server URL (default: http://localhost:8000)")
    args = parser.parse_args()

    global BASE_URL
    if args.url:
        BASE_URL = args.url

    # ── Compare mode ──────────────────────────────────────────────────────────
    if args.compare:
        with open(args.compare[0]) as f:
            r_a = json.load(f)
        with open(args.compare[1]) as f:
            r_b = json.load(f)
        label_a = Path(args.compare[0]).stem
        label_b = Path(args.compare[1]).stem
        print_report(r_a, label_a)
        print_report(r_b, label_b)
        print_comparison(r_a, label_a, r_b, label_b)
        return

    # ── Normal run ────────────────────────────────────────────────────────────
    dataset = load_dataset()
    print(f"DocuSync Benchmark v{dataset['version']} — {len(dataset['queries'])} queries")

    if not wait_for_server():
        sys.exit(1)

    with httpx.Client() as client:
        doc_id_map: dict[str, str] = {}
        if not args.no_ingest:
            doc_id_map = ingest_documents(dataset, client)
        else:
            print("Skipping ingestion (--no-ingest). Using existing documents.")

        report = evaluate(dataset, doc_id_map, client)

    report["meta"] = {
        "label":   args.label,
        "url":     BASE_URL,
        "dataset": str(DATASET_PATH),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    out_path = Path(args.output)
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"Results saved to {out_path}")

    print_report(report, args.label)


if __name__ == "__main__":
    main()
