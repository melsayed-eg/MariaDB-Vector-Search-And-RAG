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

| Mode | Queries | MRR | Recall@1 | Recall@3 | Recall@5 | Recall@10 | Precision@1 | Precision@3 | Precision@5 | Precision@10 | P50 latency (ms) | P95 latency (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| semantic | 40 | 0.8644 | 0.7250 | 0.8750 | 0.9500 | 1.0000 | 0.8000 | 0.3417 | 0.2250 | 0.1175 | 6.31 | 7.80 |

Detailed results: `reports/evaluation_semantic.md` and
`reports/evaluation_semantic.json`.

## Semantic versus hybrid comparison

Both modes were evaluated on the same 15 constrained questions.
Semantic retrieval ignored filters; hybrid retrieval applied them.

| Mode | Queries | MRR | Recall@1 | Recall@3 | Recall@5 | Recall@10 | Precision@1 | Precision@3 | Precision@5 | Precision@10 | P50 latency (ms) | P95 latency (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| semantic | 15 | 0.7551 | 0.6667 | 0.8000 | 0.8667 | 1.0000 | 0.6667 | 0.2667 | 0.1733 | 0.1000 | 6.11 | 6.64 |
| hybrid | 15 | 0.7583 | 0.6667 | 0.8000 | 0.8667 | 1.0000 | 0.6667 | 0.2667 | 0.1733 | 0.1000 | 571.55 | 579.64 |

Detailed results: `reports/evaluation_comparison.md` and
`reports/evaluation_comparison.json`.

## Reproducible benchmark

Run `make eval` against the populated local MariaDB database.

The benchmark requires 200 Wikipedia articles and 8,743 embedded chunks.
It validates the evaluation dataset, runs the 40-query semantic evaluation
and matched 15-query semantic/hybrid comparison, checks hybrid filter
compliance, and regenerates the JSON and Markdown reports.

Benchmark failures produce a nonzero exit status.

## Reproducibility metadata

`reports/evaluation_metadata.json` records the UTC execution timestamp,
Git commit and working-tree status, MariaDB and Python versions,
operating system, CPU, RAM, embedding model and dimension, SHA-256
checksums, corpus counts, K values, chunk pool, repetitions, warm-up
count, index settings, SQL search strategies, and timing methodology.

Uncommitted changes are not fully identified by the Git SHA alone.

## SQL filter compliance

Hybrid retrieval results are independently checked against stored
article metadata and returned chunk distances.

The checks cover topics, categories, included and excluded article IDs,
minimum article length, revision date, outgoing link relationships,
and maximum vector distance.

Compliance is measured per returned chunk hit. The reports include
per-query and aggregate counts, violations, and compliance rates.

Empty result sets are counted separately. They have a compliance rate
of 1.0 by convention, but do not demonstrate successful retrieval.

Any filter violation causes the benchmark to fail.

## Latency methodology and variability

Each query and mode receives one excluded warm-up request followed
by five measured retrieval requests.

Aggregate P50 and P95 latency values are calculated from per-query
mean latencies, not directly from all measured requests.

The JSON reports retain individual latency samples and sample
standard deviations. Markdown reports also summarize raw-request
mean, standard deviation, P50, and P95.

These measurements reflect one local environment and should not
be generalized to production workloads.

## Hybrid Filter Bias

The 15 constrained evaluation queries use topic filters that match the
topics of their labeled relevant articles.

This creates a favorable evaluation setting for hybrid retrieval because
the filters narrow the search space toward the expected answers.

Consequently, the comparison measures retrieval under correctly aligned
topic constraints, rather than performance under arbitrary or potentially
incorrect filters.

The results should not be interpreted as evidence that hybrid retrieval
generally outperforms semantic retrieval.

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

The full test suite passed with 584 tests. Ruff linting, formatting, and Git whitespace checks also passed.

The evaluation reports are preliminary until relevance judgments have
been independently reviewed.
