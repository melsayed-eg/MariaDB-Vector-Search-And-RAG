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
| 500/75 | 17,746 | 577 | 0.857 | 0.675 | 0.950 | 1.000 | 18.2 | 20.3 |
| 1000/150 | 8,743 | 474 | 0.864 | 0.700 | 0.950 | 1.000 | 20.7 | 37.6 |
| 1500/200 | 5,675 | 344 | 0.896 | 0.738 | 0.975 | 0.975 | 17.8 | 19.7 |

## Results: 15 constrained queries, semantic vs hybrid
When both modes run together, `run_evaluation` compares them on the 15 queries with filters.

| Setting | Semantic MRR | Hybrid MRR | Semantic p50 (ms) | Hybrid p50 (ms) | Hybrid p95 (ms) |
|---|---|---|---|---|---|
| 500/75 | 0.730 | 0.732 | 18.3 | 272.8 | 427.9 |
| 1000/150 | 0.755 | 0.758 | 26.4 | 246.5 | 371.6 |
| 1500/200 | 0.800 | 0.806 | 18.1 | 96.1 | 160.0 |

## Findings
1. **Retrieval quality differs little.** 1500/200 has the highest MRR (0.896) and Recall@1, but it is the only setting that misses one query at k=10. With 40 queries, one query moves recall by 2.5 points, so this is not a reliable ranking of the settings.
2. **Hybrid latency is lowest at 1500/200 (about 96 ms) and highest at 500/75 (about 273 ms).** Hybrid uses exact cosine ranking with SQL filters, so it scans every chunk. In the second run 1000/150 was close to 500/75 (247 ms), while the first run measured 142 ms, so latency varies between runs and a single run cannot rank the middle setting reliably. Semantic search uses the HNSW index and stays near 18 ms.
3. **Ingestion cost falls with larger chunks**, because fewer chunks are embedded (341 s versus 551 s).

## Limitations
- Small, provisional-style query set (40 queries); most questions name their article's topic, which makes retrieval easy and compresses differences.
- Article-level ranking is built from the first 30 retrieved chunks (`chunk_pool`). With smaller chunks those 30 chunks cover less text.
- A single run on one machine; latency is comparable only between these three settings, not with other machines' benchmarks.
- `all-MiniLM-L6-v2` truncates input at about 256 word pieces, so the end of a 1,500-character chunk may not influence its vector.
- The team baseline of 0.8477 was measured on the initial dataset (commit aa93732). On the final dataset (the PR #10 baseline) it is 0.8644, which matches the 1000/150 semantic MRR (0.864) of this experiment.
- The chosen default (1000/150) is unchanged by this experiment; changing it would also change article fingerprints and require re-ingestion.

- The experiment was run twice; quality results were identical, latency differed.
- CPU model not recorded (architecture x86_64, WSL2 on Windows). `git_worktree_status` in `summary.json` lists modified results files because the run regenerated them.

## Superseded first run
An earlier run evaluated only the 15 constrained queries in semantic mode because of how `run_evaluation` handles two modes. The script was fixed to also evaluate semantic mode on all 40 queries.


## Reproducing the experiment from a fresh clone
1. Install dependencies, including the embedding model library: `uv sync --extra dev --extra embeddings --locked`
2. Copy the example environment file to `.env` and set the MariaDB credentials. The experiment needs a **separate database whose name ends in `_test`** (`DB_NAME_TEST`); it refuses any other name and rebuilds that database for every setting.
3. Start MariaDB 11.8 and create the test database: `docker compose up -d --wait db`, then `bash scripts/create-test-db.sh`.
4. Run: `uv run --no-sync python -m wikirag.experiments.chunk_size` (about 25 to 60 minutes on CPU; the first run downloads the model). A dry run: add `--limit 5 --repeats 1 --out-dir /tmp/chunk_dry` (its numbers are meaningless).
5. Results are written to `results/experiments/chunk_size/`. `summary.json` records checksums, git commit, Python, operating system, CPU, MariaDB version, HNSW settings and the git working-tree status.

Results measured before this metadata existed do not contain it, and it is not reconstructed for them.

## API
The entry point is `run_chunk_size_comparison(settings, snapshot_path=..., queries_path=..., out_dir=...)` in `src/wikirag/experiments/chunk_size.py`. It calls `run_setting()` once per `(max_chars, overlap_chars)` pair and writes `summary.json`; `main()` is the command-line wrapper. The run stops with an error if any article fails to ingest, and the semantic/hybrid comparison runs with `require_compliance=True`.