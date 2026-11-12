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
For `hyb_05`, the proposed relevant articles are SQL (`29004`) and
Relational database (`25873`): both explicitly identify SQL as the
language used for relational database queries. This proposed judgment
still requires Zineb's independent confirmation.

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
| semantic | 40 | 0.8644 | 0.7125 | 0.8750 | 0.9500 | 1.0000 | 0.8000 | 0.3500 | 0.2300 | 0.1200 | 6.39 | 7.13 |

Detailed results: `reports/evaluation_semantic.md` and
`reports/evaluation_semantic.json`.

## Semantic versus hybrid comparison

Both modes were evaluated on the same 15 constrained questions.
Semantic retrieval ignored filters; hybrid retrieval applied them.

| Mode | Queries | MRR | Recall@1 | Recall@3 | Recall@5 | Recall@10 | Precision@1 | Precision@3 | Precision@5 | Precision@10 | P50 latency (ms) | P95 latency (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| semantic | 15 | 0.7551 | 0.6333 | 0.8000 | 0.8667 | 1.0000 | 0.6667 | 0.2889 | 0.1867 | 0.1067 | 6.28 | 7.07 |
| hybrid | 15 | 0.7583 | 0.6333 | 0.8000 | 0.8667 | 1.0000 | 0.6667 | 0.2889 | 0.1867 | 0.1067 | 571.30 | 609.52 |

Detailed results: `reports/evaluation_comparison.md` and
`reports/evaluation_comparison.json`.

## Reproducible benchmark

Run `make eval` against the populated local MariaDB database.

The benchmark requires 200 Wikipedia articles and 8,743 embedded chunks.
It validates the evaluation dataset, runs the 40-query semantic evaluation
and matched 15-query semantic/hybrid comparison, checks semantic
and hybrid constraint satisfaction, strictly enforces hybrid constraints,
and regenerates the JSON and Markdown reports.

Benchmark failures produce a nonzero exit status.

## Reproducibility metadata

`reports/evaluation_metadata.json` records the UTC execution timestamp,
Git commit and working-tree status, MariaDB and Python versions,
operating system, CPU, RAM, embedding model and dimension, SHA-256
checksums, corpus counts, K values, chunk pool, repetitions, warm-up
count, index settings, SQL search strategies, and timing methodology.

The recorded Git commit identifies the checked-out source revision at
benchmark execution, not necessarily the later commit that publishes
the regenerated reports. The working-tree status records modified
paths but does not fully identify their contents. Reproducing an
uncommitted benchmark therefore requires the corresponding source,
dataset, and report files, not the Git SHA alone.

## Constraint satisfaction

Both retrieval modes are independently checked against the original
question constraints using stored article metadata and chunk distances.

Semantic retrieval does not apply the constraints during retrieval;
its compliance is measured afterward. Hybrid retrieval enforces the
constraints in SQL and is independently checked afterward.

The checks cover topics, categories, included and excluded article IDs,
minimum article length, revision date, outgoing link relationships,
and maximum vector distance.

| Mode | Queries | Returned hits | Compliant hits | Violations | Compliance rate |
| --- | ---: | ---: | ---: | ---: | ---: |
| semantic | 15 | 450 | 420 | 30 | 0.9333 |
| hybrid | 15 | 450 | 450 | 0 | 1.0000 |

Compliance is measured per returned chunk hit. Empty result sets are
tracked separately and considered compliant by convention, but do not
demonstrate successful retrieval.

Any hybrid constraint violation causes the benchmark to fail.
Semantic violations are recorded for comparison rather than rejected.

Detailed per-query results are available in
`reports/evaluation_comparison.md`.

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

The full test suite passed with 586 tests. Ruff linting, formatting
(95 files), and Git whitespace checks also passed.

The evaluation reports are preliminary until relevance judgments have
been independently reviewed.
