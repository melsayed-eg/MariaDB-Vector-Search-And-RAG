# Wikipedia Retrieval Evaluation (M7)

## Dataset

The evaluation dataset is stored in `data/eval/queries.jsonl`.

- Corpus: 200 English Wikipedia Computer Science articles
- Stored vectors: 8,743 chunks
- Questions: 40
- Semantic questions: 25
- Constrained questions: 15
- Ground truth: 1–5 relevant Wikipedia article IDs per question

All referenced article IDs are validated against the committed
`data/snapshot/wikipedia_snapshot.jsonl`.

Relevance judgments are provisional pending independent review.

## Methodology

Evaluation uses MariaDB 11.8 and the
`sentence-transformers/all-MiniLM-L6-v2` embedding model.

Configuration:

- K values: 1, 3, 5, 10
- Retrieved chunk pool: 30
- Measured repetitions: 5 per query
- Warm-up: 1 retrieval per query and mode
- Metrics: Recall@K, Precision@K, MRR, P50 and P95 latency

Ranked chunk results are deduplicated into article IDs before
calculating article-level retrieval metrics.

Semantic retrieval uses MariaDB's native HNSW vector index.
Filtered hybrid retrieval uses exact cosine ranking with relational
SQL constraints.

## Full semantic evaluation

All 40 questions were evaluated without relational filters.

| Metric | Result |
|---|---:|
| MRR | 0.8477 |
| Recall@1 | 0.7000 |
| Recall@3 | 0.8750 |
| Recall@5 | 0.9500 |
| Recall@10 | 1.0000 |
| Precision@1 | 0.7750 |
| Precision@3 | 0.3417 |
| Precision@5 | 0.2250 |
| Precision@10 | 0.1175 |
| P50 latency | 11.03 ms |
| P95 latency | 11.89 ms |

Detailed results: `reports/evaluation_semantic.md` and
`reports/evaluation_semantic.json`.

## Semantic versus hybrid comparison

Both modes were evaluated on the same 15 constrained questions.
Semantic retrieval ignored filters; hybrid retrieval applied them.

| Metric | Semantic | Hybrid |
|---|---:|---:|
| Questions | 15 | 15 |
| MRR | 0.7106 | 0.7139 |
| Recall@10 | 1.0000 | 1.0000 |
| Precision@10 | 0.1000 | 0.1000 |
| P50 latency | 11.05 ms | 148.81 ms |
| P95 latency | 12.04 ms | 247.04 ms |

Detailed results: `reports/evaluation_comparison.md` and
`reports/evaluation_comparison.json`.

## Limitations

1. Relevance judgments require independent review before final approval.
2. The evaluation corpus contains only 200 Wikipedia articles.
3. Article-level ranking is derived from the first 30 retrieved chunks.
4. Hybrid and semantic retrieval use different SQL execution strategies,
   so latency differences cannot be attributed solely to filtering.
5. Latency measurements reflect one local environment and should not
   be generalized to production workloads.
6. The benchmark measures retrieval, not generated-answer correctness.
7. The 15-question comparison and 40-question semantic evaluation use
   different query sets; their aggregate metrics are not directly comparable.

## Validation

The committed evaluation dataset and snapshot are checked by automated tests.

The full local test suite passed: 574 tests.

The evaluation reports are preliminary until relevance judgments have
been independently reviewed.
