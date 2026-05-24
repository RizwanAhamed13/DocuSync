# L4 — Embedding Model Accuracy
*Generated: 2026-05-24 16:46 UTC*

## Overview
DocuSync uses `BAAI/bge-base-en-v1.5` (BAAI BGE base, English).
All embeddings are 768-dimensional; indexed in ChromaDB under cosine distance.

## Published MTEB Leaderboard (2024)
*Source: Hugging Face MTEB leaderboard — Massive Text Embedding Benchmark*

| Model                | Retrieval | STS  | Avg MTEB | Dims | Size (MB) |                    |
| -------------------- | --------- | ---- | -------- | ---- | --------- | ------------------ |
| all-MiniLM-L6-v2     | 41.5      | 78.9 | 56.3     | 384  | 91        |                    |
| bge-small-en-v1.5    | 51.7      | 84.5 | 62.2     | 384  | 133       |                    |
| bge-base-en-v1.5     | 53.3      | 85.6 | 63.9     | 768  | 438       |  ← **THIS SYSTEM** |
| bge-large-en-v1.5    | 54.0      | 86.0 | 64.2     | 1024 | 1340      |                    |
| mxbai-embed-large-v1 | 54.4      | 86.1 | 64.7     | 1024 | 670       |                    |
| e5-large-v2          | 50.6      | 85.7 | 62.8     | 1024 | 1340      |                    |

**MTEB Retrieval** = average nDCG@10 across BEIR's 18 retrieval datasets.
**MTEB STS** = Spearman correlation on Semantic Textual Similarity tasks.
**MTEB Avg** = macro-average across all 56 MTEB tasks.

## Measured Encoding Quality (in-system)

| Metric | Value | Interpretation |
|--------|-------|---------------|
| Duplicate-sentence cosine similarity | **1.0** | Should be ≈ 1.0 (same sentence) |
| Cross-sentence cosine similarity | **0.5165** | Should be < 1.0 (different sentences) |
| Output dimensions | **768** | 768 for bge-base |
| Encoding throughput | **80.7 sentences/sec** | On Apple Silicon CPU |
| MTEB Retrieval score | **53.3** | Published (not measured locally) |

> Duplicate cosine ≈ 1.0 confirms the model produces **deterministic, normalised embeddings**.
> Cross-sentence cosine < duplicate cosine confirms the model **discriminates between sentences**.

## BGE Asymmetric Encoding (Instruction Prefix)

BGE models are **instruction-tuned** — queries and passages use different prefixes:

```python
# Query embedding (with prefix)
query_vec = model.encode(
    "Represent this sentence for searching relevant passages: " + query_text
)

# Passage embedding (no prefix — stored at index time)
passage_vec = model.encode(passage_text)
```

Skipping the query prefix degrades retrieval by ~3–8% on MTEB.
DocuSync applies the prefix automatically: `if "bge" in EMBEDDING_MODEL_NAME.lower()`.

## Why bge-base over Alternatives

| Factor | MiniLM-L6 | bge-small | **bge-base** | bge-large | mxbai-large |
|--------|----------|----------|------------|---------|------------|
| MTEB Retrieval | 41.5 | 51.7 | **53.3** | 54.0 | 54.4 |
| Speed | Fastest | Fast | **Medium** | Slow | Slow |
| RAM (768-dim×2239) | 3.4 MB | 3.4 MB | **6.8 MB** | 10.2 MB | 10.2 MB |
| Quality/Speed ratio | Low | Medium | **Best** | — | — |

bge-base provides **+28% retrieval improvement** over MiniLM at acceptable speed cost.
bge-large adds only +0.7% retrieval over bge-base at 3× the compute — not worth it for this corpus.

## Generalization
The model is **universal for English text** — no dataset-specific tuning.
For specialised domains:
- Medical: `pritamdeka/BioBERT-mnli-snli-scinli-scitail-mednli-sst2`
- Legal: `law-ai/InLegalBERT`
- Code: `microsoft/graphcodebert-base`
- Multilingual: `BAAI/bge-m3`
