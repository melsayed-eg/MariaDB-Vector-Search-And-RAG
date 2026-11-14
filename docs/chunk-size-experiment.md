# Chunk-size and overlap experiment

## Question
Does the chunk size (and overlap) change retrieval quality, latency and ingestion cost?

## Method
- Settings compared (max_chars / overlap_chars): 500/75, 1000/150, 1500/200.
- For each setting the 200-article snapshot was re-ingested into a rebuilt `_test` MariaDB database with `all-MiniLM-L6-v2` (384 dimensions), then evaluated with the existing `run_evaluation` on `data/eval/queries.jsonl` (40 queries: 25 semantic, 15 constrained).
- Metrics: Recall@k, Precision@k and MRR at k = 1, 3, 5, 10; p50/p95 latency over 5 measured repetitions.
- Code: `src/wikirag/experiments/chunk_size.py`. Run: `uv run --no-sync python -m wikirag.experiments.chunk_size`.
- Reproducibility: snapshot SHA-256 `d64afac28a918ad16639a1e534f4d3bf472ec48327927c4ed52ae8a180211b2c`, query file SHA-256 `26e39637e01a739697721a8187539bb93b256af7b26eda5a3f172884b13e4a8c`, git commit and settings are recorded in `results/experiments/chunk_size/summary.json`.

## Results: semantic mode, all 40 queries

| Setting | Chunks | Ingest (s) | MRR | Recall@1 | Recall@5 | Recall@10 | p50 (ms) | p95 (ms) |
|---|---|---|---|---|---|---|---|---|
| 500/75 | 17,746 | 551 | 0.857 | 0.675 | 0.950 | 1.000 | 18.1 | 21.1 |
| 1000/150 | 8,743 | 459 | 0.864 | 0.700 | 0.950 | 1.000 | 17.8 | 19.0 |
| 1500/200 | 5,675 | 341 | 0.896 | 0.738 | 0.975 | 0.975 | 17.8 | 19.3 |

## Results: 15 constrained queries, semantic vs hybrid
When both modes run together, `run_evaluation` compares them on the 15 queries with filters.

| Setting | Semantic MRR | Hybrid MRR | Semantic p50 (ms) | Hybrid p50 (ms) | Hybrid p95 (ms) |
|---|---|---|---|---|---|
| 500/75 | 0.730 | 0.732 | 18.0 | 262.2 | 437.1 |
| 1000/150 | 0.755 | 0.758 | 18.3 | 141.6 | 221.5 |
| 1500/200 | 0.800 | 0.806 | 17.5 | 93.4 | 154.2 |

## Findings
1. **Retrieval quality differs little.** 1500/200 has the highest MRR (0.896) and Recall@1, but it is the only setting that misses one query at k=10. With 40 queries, one query moves recall by 2.5 points, so this is not a reliable ranking of the settings.
2. **Hybrid latency grows with the number of chunks** (about 93 ms at 5,675 chunks to 262 ms at 17,746). Hybrid uses exact cosine ranking with SQL filters, so it scans every chunk. Semantic search uses the HNSW index and stays near 18 ms for all settings.
3. **Ingestion cost falls with larger chunks**, because fewer chunks are embedded (341 s versus 551 s).

## Limitations
- Small, provisional-style query set (40 queries); most questions name their article's topic, which makes retrieval easy and compresses differences.
- Article-level ranking is built from the first 30 retrieved chunks (`chunk_pool`). With smaller chunks those 30 chunks cover less text.
- A single run on one machine; latency is comparable only between these three settings, not with other machines' benchmarks.
- `all-MiniLM-L6-v2` truncates input at about 256 word pieces, so the end of a 1,500-character chunk may not influence its vector.
- The 1000/150 MRR (0.864) differs slightly from the team baseline (0.8477 in `reports/`); the reason has not been confirmed.
- The chosen default (1000/150) is unchanged by this experiment; changing it would also change article fingerprints and require re-ingestion.

## Superseded first run
An earlier run evaluated only the 15 constrained queries in semantic mode because of how `run_evaluation` handles two modes. The script was fixed to also evaluate semantic mode on all 40 queries.