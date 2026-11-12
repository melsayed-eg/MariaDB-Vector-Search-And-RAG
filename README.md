A project for area 4, "Vector search and RAG, natively" for the [MariaDB student database projects, 2026-09](https://mariadb.org/bachelor_hackathon_2026-09/).

# MariaDB WikiRAG

Wikipedia semantic search, relational SQL filtering, and retrieval-augmented question answering using MariaDB 11.8's native vector capabilities.

## 1. Project overview

WikiRAG demonstrates how Wikipedia article metadata and text embeddings can live in the same transactional MariaDB database.

It combines:

- Native `VECTOR(384)` storage and HNSW indexing.
- Semantic retrieval using `VEC_DISTANCE_COSINE`.
- Hybrid retrieval using vector similarity and SQL predicates together.
- Relational article metadata, categories, and Wikipedia links.
- Transactional ingestion of article records and embeddings.
- Extractive retrieval-augmented generation (RAG) with citations.
- Measured retrieval quality, latency, and database-depth experiments.

The project does not require a separate vector database.

The core question is whether a relational database with native vector support can provide useful semantic search while retaining SQL filtering, joins, and transactional consistency.

## 2. Main findings

The implemented system operates on a reproducible Wikipedia corpus containing:

| Property | Value |
| --- | ---: |
| Wikipedia articles | 200 |
| Embedded text chunks | 8,743 |
| Computer Science topics | 7 |
| Stored Wikipedia categories | 1,056 |
| Embedding dimensions | 384 |
| Ground-truth evaluation questions | 40 |
| Constrained evaluation questions | 15 |

The corpus covers algorithms, databases, AI and machine learning, systems and networks, programming languages and software engineering, theory and security, and computing history.

The experiments and evaluation demonstrate:

1. Native cosine HNSW retrieval works on the stored Wikipedia vectors.
2. SQL predicates and vector-distance ranking can be combined within one MariaDB statement.
3. Article metadata and vectors become visible together after a transaction commits.
4. Retrieval quality and latency can be measured using labeled questions rather than subjective descriptions.
5. HNSW index usage depends on the SQL distance expression and query plan.

The hybrid implementation prioritizes correct relational filtering. It currently uses exact cosine ranking after SQL filters, which can be substantially slower than the HNSW-indexed semantic path.

These findings are specific to the evaluated corpus, queries, SQL implementations, and test environments.

## 3. Technology stack

| Component | Technology |
| --- | --- |
| Language | Python 3.11+ |
| Tested development environment | Python 3.14 on Ubuntu WSL |
| Database | MariaDB 11.8 LTS |
| Storage engine | InnoDB |
| Vector type | `VECTOR(384)` |
| Vector index | Native HNSW |
| Distance function | `VEC_DISTANCE_COSINE` |
| Embedding model | `sentence-transformers/all-MiniLM-L6-v2` |
| RAG generator | Extractive generator |
| Dependencies | uv and `uv.lock` |
| Containers | Docker Compose |
| Tests | pytest |
| Code quality | Ruff |

A generative LLM is not required to run the default application. The current RAG implementation uses retrieved Wikipedia passages and an extractive generator.

## 4. Quick start

### Prerequisites

Install:

- Git
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- Docker with Docker Compose
- GNU Make

Internet access is required for the initial Python dependency and embedding-model downloads.

### Clone and configure

```bash
git clone https://github.com/melsayed-eg/MariaDB-Vector-Search-And-RAG.git
cd MariaDB-Vector-Search-And-RAG
cp .env.example .env
```

Open `.env` and replace the example MariaDB passwords with your own local credentials.

Never commit `.env`, database passwords, or API keys.

### Automated setup

```bash
make setup
```

This command:

1. Installs locked Python dependencies, including CPU-based embeddings.
2. Starts MariaDB and waits for a healthy database container.
3. Initializes or verifies the canonical schema.
4. Ingests the committed Wikipedia snapshot.
5. Prepares the separate integration-test database.
6. Displays the resulting corpus statistics.

The project uses the local MariaDB port `13307` by default.

The initial setup may download the MiniLM model. A GPU is not required.

The Wikipedia snapshot is included at:

`data/snapshot/wikipedia_snapshot.jsonl`

Re-running setup does not reset the main database. Unchanged articles are identified by deterministic fingerprints and skipped.

For detailed setup instructions and troubleshooting, see [docs/setup.md](docs/setup.md).

### Run the full demo

After setup:

```bash
make demo
```

This launches a read-only demonstration covering database statistics, semantic search, hybrid SQL filtering, and a cited RAG answer.

The demonstration requires the complete 200-article, 8,743-chunk corpus.

It does not modify database records or regenerate evaluation reports.

## 5. Command-line interface

The project provides the following CLI commands.

| Command | Purpose |
| --- | --- |
| `init-db` | Initialize or verify the MariaDB schema |
| `build-snapshot` | Fetch Wikipedia articles into a JSONL snapshot |
| `ingest` | Chunk, embed, and store snapshot articles |
| `stats` | Display corpus statistics |
| `search` | Execute semantic or hybrid retrieval |
| `ask` | Produce a source-cited extractive RAG answer |
| `evaluate` | Run the retrieval evaluation benchmark |
| `experiment` | Run native-vector database experiments |

### Semantic search

```bash
uv run --extra embeddings python -m wikirag.cli search \
  "How does quicksort work?" --top-k 3
```

Semantic search embeds the query and retrieves matching chunks using MariaDB's HNSW-eligible cosine search.

### Hybrid SQL and vector search

```bash
uv run --extra embeddings python -m wikirag.cli search \
  "How does heapsort work?" \
  --mode hybrid \
  --article-id 13995 \
  --top-k 3
```

This example applies an article-ID predicate in SQL while ranking matching chunks by native cosine distance.

Additional hybrid filters include topics, Wikipedia categories, excluded article IDs, minimum article length, revision date, outgoing links, and maximum vector distance.

Hybrid mode requires at least one active SQL filter.

### RAG question answering

```bash
uv run --extra embeddings python -m wikirag.cli ask \
  "How does quicksort work?"
```

The RAG pipeline retrieves Wikipedia chunks, builds a bounded context, selects relevant passages through an extractive generator, and displays source citations.

The default generator operates without a remote LLM API.

Its answers are grounded in retrieved text, but sentence selection can sometimes produce awkward or incomplete explanations. Retrieval evaluation does not establish generated-answer correctness.

### Corpus statistics

```bash
uv run python -m wikirag.cli stats
```

To display category names:

```bash
uv run python -m wikirag.cli stats \
  --min-category-articles 5 --show-categories
```

For all CLI options, use:

```bash
uv run python -m wikirag.cli --help
```

## 6. Wikipedia data and ingestion

The corpus contains 200 English Wikipedia articles in seven Computer Science topics.

Article titles are defined in `data/seed_titles.csv`.

The committed snapshot stores article identifiers, titles, canonical URLs, revision metadata, categories, outgoing links, topics, and text.

Source content is obtained through the MediaWiki API. The committed JSONL snapshot provides a reproducible input even when live Wikipedia articles change later.

### Rebuild a snapshot

To fetch a new snapshot without overwriting the committed one:

```bash
uv run python -m wikirag.cli build-snapshot \
  --seed data/seed_titles.csv \
  --output data/tmp/new_wikipedia_snapshot.jsonl
```

A newly fetched snapshot may contain later Wikipedia revisions, so it is not guaranteed to reproduce the original corpus or benchmark results.

### Chunking and embeddings

The ingestion pipeline uses:

| Parameter | Value |
| --- | --- |
| Maximum chunk size | 1,000 characters |
| Target chunk overlap | 150 characters |
| Embedding model | `all-MiniLM-L6-v2` |
| Embedding dimension | 384 |

Chunk boundaries prefer paragraph, line, sentence, or word boundaries where possible.

The 1,000-character limit keeps passages reasonably focused while avoiding excessively small chunks. The 150-character overlap helps retain context across boundaries, at the cost of some duplicated content and embeddings.

MiniLM was chosen as a compact, CPU-capable sentence embedding model with a 384-dimensional output compatible with the MariaDB vector schema. This is a practical design choice, not a claim that it is the highest-quality embedding model.

Ingestion is idempotent for unchanged content, model settings, and chunking settings.

Article metadata, categories, links, and chunks are maintained through the repository's transactional database operations.

For acquisition, cleaning, chunking, and licensing details, see [docs/ingestion.md](docs/ingestion.md).

## 7. Database schema and design

The canonical schema is defined in [sql/001_schema.sql](sql/001_schema.sql).

| Table | Responsibility |
| --- | --- |
| `embedding_meta` | Records the embedding model and dimension |
| `articles` | Stores Wikipedia metadata and searchable relational attributes |
| `chunks` | Stores text chunks and native vector embeddings |
| `categories` | Normalizes Wikipedia category names |
| `article_categories` | Links articles to multiple categories |
| `links` | Records outgoing Wikipedia links and resolved target articles |

### Why this schema?

Article metadata is stored once in `articles`, rather than repeated in every chunk.

Each chunk references its parent article through a foreign key. This allows semantic results to be joined back to titles, URLs, revisions, and other article attributes.

Separate category and link tables support many-to-many categories and Wikipedia graph relationships using ordinary SQL.

The `embedding_meta` table checks that ingestion uses the embedding model and dimension expected by the stored vectors.

InnoDB transactions keep vector rows and their related metadata within one database, avoiding a separate vector-store synchronization step.

The main vector definition is:

```sql
embedding VECTOR(384) NOT NULL,
VECTOR INDEX (embedding) M=16 DISTANCE=cosine
```

The index uses cosine distance and HNSW `M=16`, the configured graph-connectivity parameter. This balances index complexity against approximate-search capability without claiming that the setting is optimal for every workload.

## 8. Native semantic and hybrid SQL

### Indexed semantic search

For unfiltered retrieval, the database ranks chunks using `VEC_DISTANCE_COSINE` in an HNSW-eligible query and joins the ranked results back to the `articles` table.

The application implementation is in:

- `src/wikirag/db/queries.py`
- `src/wikirag/db/repository.py`

### Hybrid retrieval in one SQL statement

The following simplified example illustrates the implemented filtered-search approach. The `%s` placeholders are bound using PyMySQL; this is application SQL, not a standalone MariaDB client script.

```sql
SELECT
    c.chunk_id,
    a.title,
    c.text,
    VEC_DISTANCE_COSINE(
        c.embedding,
        VEC_FromText(%s)
    ) AS distance
FROM chunks AS c IGNORE INDEX (embedding)
JOIN articles AS a
    ON a.article_id = c.article_id
WHERE a.length_chars > %s
  AND EXISTS (
      SELECT 1
      FROM article_categories AS ac
      JOIN categories AS cat
          ON cat.category_id = ac.category_id
      WHERE ac.article_id = a.article_id
        AND LOWER(cat.name) = %s
  )
ORDER BY distance ASC
LIMIT %s;
```

The vector-distance calculation, article metadata join, and relational predicates operate within the same MariaDB statement.

The application also supports topic filters, revision-date filters, linked-article constraints, and other validated predicates.

**Implementation tradeoff:** filtered retrieval intentionally excludes the HNSW index and performs exact cosine ranking after relational filtering. This avoids selecting top-K vectors before applying restrictive filters, which could return too few eligible results.

Consequently, the hybrid SQL demonstration is not a claim that its current implementation is faster than indexed semantic search.

For example queries and detailed database design, see:

- [sql/002_example_queries.sql](sql/002_example_queries.sql)
- [docs/database.md](docs/database.md)

## 9. Retrieval evaluation

The evaluation dataset is stored in:

`data/eval/queries.jsonl`

It contains 40 labeled questions with known relevant Wikipedia article IDs.

Of these, 25 are semantic-only questions and 15 carry constraints. The complete semantic benchmark evaluates all 40 questions. The semantic/hybrid comparison uses the same 15 constrained questions for both modes.

Zineb reviewed and approved the evaluation questions and relevance labels recorded in the repository's evaluation documentation.

### Reproduce the benchmark

After `make setup`:

```bash
make eval
```

The benchmark requires exactly 200 articles and 8,743 chunks.

It measures:

- Article-level Recall@K and Precision@K for K = 1, 3, 5, 10.
- Mean reciprocal rank (MRR).
- P50 and P95 retrieval latency.
- Relational filter compliance.
- Repeated query measurements and latency variability.

Each query and mode receives one excluded warm-up, followed by five measured retrieval requests.

**Note:** Running `make eval` regenerates the report files in `reports/`. Review those changes before committing.

### Recorded five-repeat results

The following results come from the documented benchmark in `docs/evaluation.md`.

| Evaluation | Queries | MRR | Recall@5 | Recall@10 | P50 latency |
| --- | ---: | ---: | ---: | ---: | ---: |
| Full semantic | 40 | 0.8644 | 0.9500 | 1.0000 | 6.50 ms |
| Semantic, constrained subset | 15 | 0.7551 | 0.8667 | 1.0000 | 6.16 ms |
| Hybrid, constrained subset | 15 | 0.7583 | 0.8667 | 1.0000 | 563.56 ms |

For the constrained comparison, the recorded filter-compliance results were 420 of 450 semantic hits and 450 of 450 hybrid hits.

The semantic mode did not enforce filters, while hybrid mode applied them in SQL.

The substantially higher hybrid latency reflects a different SQL execution strategy that performs exact vector ranking. The results should not be interpreted as evidence that hybrid retrieval is generally faster or more accurate.

The recorded recall values apply only to this evaluated question set, not arbitrary user questions.

Full evaluation evidence:

- [Evaluation methodology and limitations](docs/evaluation.md)
- [Full semantic report](reports/evaluation_semantic.md)
- [Semantic versus hybrid report](reports/evaluation_comparison.md)
- [Reproducibility metadata](reports/evaluation_metadata.json)

Timing measurements depend on the environment and should be repeated when comparing results across machines.

## 10. MariaDB depth experiments

Beyond basic vector search, the project investigates MariaDB-specific behavior.

### Experiment C — Distance-expression and index mismatch

The experiment compares direct cosine ranking, Euclidean distance, and a wrapped cosine expression.

SQL `EXPLAIN` plans are used to check whether the native HNSW index is selected.

In the verified experiments, direct cosine ranking selected the index while the alternative expressions did not.

This shows why a VECTOR column alone is not proof that a query uses HNSW.

### Experiment D — Transaction visibility

Independent database connections observe article metadata and vector results before commit, after rollback, after commit, and after cleanup.

The experiment covers both `REPEATABLE READ` and `READ COMMITTED` isolation levels.

The experiment is restricted to a dedicated `_test` database.

### Experiment E — HNSW cache-size behavior

A separate MariaDB container and synthetic 6,000-vector corpus were used to compare HNSW cache limits over five restart cycles.

| Cache limit | Mean warm latency | P95 latency |
| --- | ---: | ---: |
| 1 MiB | 6.018 ms | 8.516 ms |
| 16 MiB | 2.878 ms | 5.023 ms |
| 64 MiB | 3.016 ms | 4.683 ms |

These are recorded synthetic benchmark results, not measurements of Wikipedia answer quality. No universal optimal cache setting is claimed.

Complete experiment methods, safeguards, and results:

- [Database experiments](docs/database_experiments.md)
- [Committed HNSW cache report](results/experiments/cache_size_synthetic.json)

## 11. Testing and reproducibility

Run unit tests:

```bash
make test-unit
```

Prepare the test database:

```bash
make setup-test-db
```

Run database integration tests:

```bash
make test-db
```

Run all tests:

```bash
make test
```

Check code quality:

```bash
make lint
```

The project also contains unit tests for CLI behavior, evaluation components, database logic, and the read-only demonstration.

Tests that exercise MariaDB use a separate test database rather than the main Wikipedia corpus.

### Database isolation

| Database | Purpose |
| --- | --- |
| `wikirag` | Main Wikipedia corpus |
| `wikirag_test` | Integration and transaction experiments |
| `wikirag_cache_test` | Separate synthetic cache benchmark |

The cache experiment uses a dedicated Docker service on local port `13308`.

Do not use `docker compose down -v` during normal development; removing volumes can permanently delete stored database data.

### Environment details

The team has tested the implementation using MariaDB 11.8.9. MariaDB is started from the `mariadb:11.8` Docker image.

Python dependencies are resolved through `uv.lock`.

Reproducibility metadata for the reported retrieval measurements includes the MariaDB version, embedding model, corpus checksums, query settings, timing methodology, and environment information.

## 12. Known limitations

- The Wikipedia corpus covers 200 selected articles, not all of Wikipedia.
- The labeled questions are curated and may not represent arbitrary user questions.
- The default RAG generator is extractive. It can produce awkward or incomplete prose despite retrieving relevant sources.
- Retrieval metrics do not measure generated-answer correctness.
- Filtered hybrid retrieval currently uses exact cosine ranking and can be considerably slower than HNSW-indexed semantic retrieval.
- The constrained evaluation questions use filters aligned with their relevant articles, which favors the tested hybrid setting.
- Reported latency measurements depend on the database, host hardware, and experimental conditions.
- Synthetic cache measurements do not establish performance on production-scale Wikipedia datasets.

These limitations guide future improvements, including answer quality, alternative filtered-search strategies, larger evaluation sets, and additional performance testing.

## 13. Project structure

```text
src/wikirag/
  db/                  MariaDB schema, repository, SQL and diagnostics
  ingestion/           Wikipedia fetching, cleaning, chunking, ingestion
  evaluation/          Ground-truth retrieval metrics and reporting
  retrieval/           Semantic and hybrid retrieval
  rag/                 Context building and extractive answer generation
  experiments/         MariaDB depth experiments
  cli.py               Command-line interface

data/
  seed_titles.csv      Wikipedia corpus specification
  snapshot/            Reproducible article snapshot
  eval/                Ground-truth questions

sql/                   Schema and worked MariaDB queries
scripts/               Demo, benchmarks and database preparation
tests/                 Unit, integration and end-to-end tests
reports/               Retrieval evaluation reports
results/experiments/   Database experiment evidence
docs/                  Architecture, setup, ingestion and evaluation
```

## 14. Team responsibilities

| Contributor | Main responsibilities |
| --- | --- |
| Tanya | Database schema, MariaDB repository, native SQL search, CLI, integration, and coordination |
| Zineb | Wikipedia corpus, snapshot, cleaning, chunking, embeddings, and ingestion |
| Marwan | Retrieval, RAG pipeline, retrieval evaluation, and experimental analysis |

All contributors participate in interface reviews, testing, documentation, and pull-request reviews.

Development uses feature branches and reviewed pull requests into `main`. See [CONTRIBUTING.md](CONTRIBUTING.md).

## 15. Further documentation

- [Automated setup and demo](docs/setup.md)
- [Database architecture and schema](docs/database.md)
- [Ingestion and corpus methodology](docs/ingestion.md)
- [Shared interfaces](docs/interfaces.md)
- [Retrieval evaluation](docs/evaluation.md)
- [Database depth experiments](docs/database_experiments.md)
- [Contribution workflow](CONTRIBUTING.md)
- [Official MariaDB Area 4 assignment](https://mariadb.org/bachelor_hackathon_2026-09/)
