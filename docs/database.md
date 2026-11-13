
# MariaDB Database Design and Verification

> **Scope:** Implemented MariaDB schema, database repository, transactional Wikipedia ingestion, native vector search, SQL hybrid retrieval, evaluation evidence, and database experiments for WikiRAG (Area 4: *Vector search and RAG, natively*).
>
> **Sources of truth:** The official MariaDB Area 4 assignment defines the submission requirements; the checked-in SQL and Python implementation define actual behavior. See [System Architecture](architecture.md), [Shared Interfaces](interfaces.md), and [Database Experiments](database_experiments.md) for related details.

## 1. Purpose and implementation status

The project demonstrates semantic retrieval over real Wikipedia content **without a separate vector database**. MariaDB 11.8 stores article metadata, categories, outgoing links, text chunks, and embedding vectors in one InnoDB database. A single SQL query can rank by cosine distance while also applying ordinary relational predicates.

The implemented database layer supports:

- A native `VECTOR(384)` column and cosine HNSW vector index.
- Article-level atomic ingestion with skip/update behavior and rollback.
- Native semantic nearest-neighbor retrieval through `VEC_DISTANCE_COSINE`.
- SQL-filtered hybrid retrieval using category, topic, article metadata, and link relations.
- Exact cosine search for comparisons with the HNSW-eligible semantic path.
- Embedding-model compatibility checks and session-scoped HNSW search-breadth controls.
- Isolated MariaDB integration tests and database-depth experiments.

The committed Wikipedia snapshot has been ingested as **200 articles, 8,743 chunks, seven topics, and 1,056 categories**. Retrieval quality and latency have been evaluated on **40 labeled questions**, including a matched **15-question semantic-versus-hybrid comparison**. These observations establish functioning retrieval on the chosen corpus; they do not establish performance at Wikipedia-wide scale.

## 2. Environment and reproducibility

| Setting | Implementation or recorded value |
| --- | --- |
| Database engine | MariaDB 11.8, InnoDB |
| Recorded server version | `11.8.9-MariaDB-ubu2404` |
| Docker image | `mariadb:11.8` |
| Python tooling | Python 3.14.4 tested locally; `uv` and committed `uv.lock` |
| Main database | `wikirag` by default (`DB_NAME`) |
| Integration-test database | `wikirag_test` by default (`DB_NAME_TEST`) |
| Main host port | `127.0.0.1:13307` by default |
| Embedding model | `sentence-transformers/all-MiniLM-L6-v2` |
| Embedding dimensions | 384 |
| Vector index | `VECTOR INDEX (embedding) M=16 DISTANCE=cosine` |

Each contributor must create a private `.env` from `.env.example` and replace the sample passwords. **Never commit `.env`, credentials, or API keys.** Existing environment variables override `.env` values. The embedding factory uses the configured model identifier, and database metadata checks prevent accidental use of a different model against stored vectors.

For a fresh clone, run the following from the repository root:

```bash
cp .env.example .env
# Edit .env and replace the example passwords.
make setup
make demo
make test
make lint
```

`make setup` installs the locked development and embedding dependencies, starts and health-checks MariaDB, initializes or verifies the schema, ingests the committed Wikipedia snapshot, prepares the isolated test database, and displays corpus statistics. It is designed to avoid destroying existing main-database data. `make demo` performs a read-only demonstration of statistics, semantic search, hybrid search, and cited RAG.

Useful commands:

```bash
make up
make version
make setup-test-db
make test-unit
make test-db
make test
make lint
make down
```

`make down` does not delete the database volume. **Do not use `docker compose down -v` during normal work**, because that removes persistent data. See [Setup and Reproduction](setup.md) for additional instructions.

## 3. Schema and relational design

The canonical DDL is [`sql/001_schema.sql`](../sql/001_schema.sql). `db/schema.py::init_schema()` creates or verifies it; `verify_schema()` checks columns, required foreign keys, `VECTOR(384)`, and the cosine vector index. There are **six InnoDB tables**.

```text
embedding_meta                       articles
(model and dimension)                (Wikipedia page ID, metadata)
                                         |
                      +------------------+------------------+
                      |                  |                  |
                   chunks       article_categories       links
                (VECTOR(384))      (article FK)         (source FK)
                      |                  |                  |
               cosine HNSW          categories       target article ID
                                    (category FK)       (nullable FK)
```

### 3.1 `embedding_meta`

The single row with `id = 1` records `model_name`, `embedding_dim`, and creation time. `WikiRepository.ensure_embedding_meta()` inserts metadata when needed, accepts matching values, and rejects incompatible models or dimensions. This ensures that query vectors and stored chunk vectors use the same embedding space.

### 3.2 `articles`

Each article uses the stable Wikipedia `article_id` as its primary key. Other columns include:

- `title` with case-sensitive `utf8mb4_bin` uniqueness, and the canonical `url`.
- `revision_id`, `revised_at`, `fetched_at`, and `ingested_at` for provenance.
- `length_chars` for article-length predicates.
- `fingerprint` for detecting unchanged ingestion inputs.
- `topic` for corpus-topic predicates and `language` (default `en`).

Secondary indexes support lookups by `topic`, `revised_at`, and `length_chars`. Article revision timestamps used by the Python model are naive UTC values.

### 3.3 `chunks`

Each text chunk has a generated `chunk_id`, a parent `article_id`, zero-based `chunk_index`, optional `section_title`, `text`, `char_count`, and a required `embedding VECTOR(384)` column.

The schema includes:

```sql
UNIQUE KEY uq_chunks_article_idx (article_id, chunk_index),
CONSTRAINT fk_chunks_article
    FOREIGN KEY (article_id)
    REFERENCES articles (article_id)
    ON DELETE CASCADE,
VECTOR INDEX (embedding) M=16 DISTANCE=cosine
```

The article/position uniqueness constraint supports deterministic chunk order and neighbor lookup. The index explicitly selects cosine distance and `M=16` rather than relying on MariaDB's server defaults. **`M=16` is the implemented setting, not a proven optimal value.**

### 3.4 `categories` and `article_categories`

`categories` has a generated primary key and a case-sensitive unique category name. `article_categories` is a many-to-many bridge with composite primary key `(article_id, category_id)` and an index on `category_id`. Foreign keys prevent orphan memberships and support relational category predicates without storing an opaque category JSON array in `articles`.

### 3.5 `links`

The primary key `(source_article_id, target_title)` preserves outgoing Wikipedia links, even when targets are outside the selected corpus. `source_article_id` references `articles` with `ON DELETE CASCADE`. Nullable `target_article_id` references `articles` with `ON DELETE SET NULL` and is populated when `resolve_links()` finds the target among ingested articles.

This design supports the official assignment's **linked-from-another-article** constraint through SQL joins and `EXISTS` predicates.

## 4. Repository interfaces and transactions

`src/wikirag/db/connection.py` owns connection creation and the `transaction()` context manager. `src/wikirag/db/repository.py::WikiRepository` exposes the database API consumed by ingestion, retrieval, RAG, and evaluation. Its public signatures must remain consistent with [Shared Interfaces](interfaces.md).

Key operations include:

| Operation | Behavior |
| --- | --- |
| `ensure_embedding_meta()` | Store or verify model name and dimensions |
| `get_fingerprint()` | Check whether article content/settings have changed |
| `ingest_article()` | Atomically insert, update, or skip article and dependent records |
| `resolve_links()` | Resolve outgoing link titles to in-corpus article IDs |
| `get_article()` / `get_article_by_title()` | Fetch metadata, categories, and links |
| `get_chunk()` / `get_neighbor_chunks()` | Retrieve chunk text and adjacent chunks |
| `list_topics()` / `list_categories()` | Expose available relational filter values |
| `count_articles()` / `count_chunks()` | Report corpus statistics |
| `search_chunks()` | Indexed-eligible semantic or SQL-filtered hybrid search |
| `search_chunks_exact()` | Exact cosine search without HNSW |
| `set_ef_search()` | Update the session's HNSW search breadth |
| `delete_article()` | Remove article and indexed child chunks atomically |

### 4.1 Atomic article ingestion

`WikiRepository.ingest_article()` validates the article and its chunks **before beginning database mutation**. Inside one transaction, it locks the existing article fingerprint, then:

1. Returns `skipped` without replacing data if the fingerprint matches.
2. Inserts metadata for a new article, or updates metadata for a changed article.
3. For updates, removes old dependent chunks, category memberships, and outgoing links.
4. Inserts the new chunks and vectors, category memberships, and outgoing links.
5. Commits all changes together, or rolls back on failure.

Chunk vectors are stored with MariaDB's `VEC_FromText()`, and vector round-tripping has been tested with `VEC_ToText()`. After processing the snapshot, the ingestion pipeline calls `resolve_links()` once in a **separate transaction**.

Because indexed child-vector deletion caused a reproduced visibility problem in the database experiment, updates and article deletion explicitly remove `chunks` before deleting their parent articles rather than relying solely on the foreign-key cascade. The foreign keys remain as database integrity safeguards. This is a project-level mitigation of observed behavior, **not a claim that MariaDB itself has been fixed**.

Failed article writes roll back together, preventing partially replaced metadata and vectors. Tests exercise intentional failures and confirm the previous committed article data remains intact.

### 4.2 Title and parameter conventions

`get_article_by_title()` and link resolution use case-sensitive matching consistent with the schema's binary title collation. Wikipedia titles must therefore be normalized consistently before storage. SQL query **values use bound parameters**; only trusted SQL structure and placeholder lists are constructed dynamically.

## 5. Embeddings and Wikipedia ingestion

The committed input is [`data/snapshot/wikipedia_snapshot.jsonl`](../data/snapshot/wikipedia_snapshot.jsonl), defined by [`data/seed_titles.csv`](../data/seed_titles.csv). The snapshot captures source revisions so the same data can be ingested again without refetching a changing Wikipedia page.

The pipeline in `src/wikirag/ingestion/pipeline.py`:

1. Checks embedding-model metadata against the embedder.
2. Loads and cleans each Wikipedia article.
3. Computes a SHA-256 fingerprint of the cleaned text, chunking settings, and embedding-model name.
4. Checks the stored fingerprint **before embedding** and skips unchanged articles.
5. Splits changed articles into chunks of at most **1,000 characters**, with an intended **150-character overlap**.
6. Generates L2-normalized **384-dimensional** vectors using MiniLM on CPU.
7. Persists the article and related records via the repository transaction.
8. Records per-article failures and resolves in-corpus links after processing.

Chunking prefers paragraph, newline, sentence, and word boundaries; overlap is character-based rather than tokenizer-based. The stored model identity is checked again when retrieving so ingestion and queries do not silently use incompatible embedding spaces. See [Ingestion](ingestion.md).

## 6. Native semantic search and SQL hybrid retrieval

There are two intentionally different retrieval paths.

### 6.1 Indexed-eligible semantic retrieval

The unfiltered query ranks stored vectors first using MariaDB's native cosine distance, then joins metadata:

```sql
SELECT ranked.chunk_id, ranked.article_id, a.title, a.url,
       ranked.distance
FROM (
    SELECT c.chunk_id, c.article_id,
           VEC_DISTANCE_COSINE(
               c.embedding, VEC_FromText(%s)
           ) AS distance
    FROM chunks AS c
    ORDER BY VEC_DISTANCE_COSINE(
        c.embedding, VEC_FromText(%s)
    ) ASC
    LIMIT %s
) AS ranked
JOIN articles AS a
    ON a.article_id = ranked.article_id
ORDER BY ranked.distance ASC,
         ranked.article_id ASC,
         ranked.chunk_id ASC;
```

The production query in `db/queries.py` additionally returns chunk position, section title, and text. During development, `EXPLAIN` showed that a direct vector-ranking query chose the `embedding` index, while a join-before-ranking version did not. The **rank-first, join-second** shape retained the native-vector index in subsequent tests.

### 6.2 SQL-filtered hybrid retrieval

`db/queries.py::build_hybrid_search_query()` constructs **one parameterized SQL statement** that applies relational predicates and cosine-distance ranking. It supports:

| Shared `SearchFilters` field | SQL semantics |
| --- | --- |
| `topics` | Match any listed topic, case-insensitively |
| `categories` | Match any listed category through the many-to-many bridge |
| `article_ids` | Include selected article IDs |
| `exclude_article_ids` | Exclude selected article IDs |
| `min_length_chars` | Require `a.length_chars > value` |
| `edited_since` | Require `a.revised_at >= value` |
| `linked_from_article_id` | Restrict results to articles linked from a source article |
| `max_distance` | Exclude hits exceeding a cosine-distance threshold |

Different filter fields combine with **AND**; multiple allowed values within a field combine with **OR**. `SearchFilters.validate()` rejects invalid types, identifiers, timestamps, and thresholds. The real repository and in-memory test repository use the same validation contract.

**Important performance distinction:** Filtered hybrid queries currently include:

```sql
FROM chunks AS c IGNORE INDEX (embedding)
```

They rank the **eligible filtered rows exactly**, rather than first taking an HNSW top-K subset that might omit valid matches. This avoids selective-filter top-K under-fill and was verified through controlled MariaDB integration tests. It is a deliberate correctness-versus-speed tradeoff: **hybrid SQL retrieval is database-native, but this filtered path is not HNSW-accelerated**.

### 6.3 Exact baseline and HNSW session settings

`WikiRepository.search_chunks_exact()` uses `VEC_DISTANCE_COSINE` and explicitly excludes the vector index. Both exact and indexed semantic search return shared `SearchHit` objects, with:

```python
score = 1.0 - distance
```

A controlled four-vector integration test confirmed agreement on the top-three identifiers, order, distances, and scores. This is functional evidence, **not** a corpus-scale approximate-versus-exact recall measurement.

`WikiRepository.set_ef_search(value)` accepts integers from **1 to 10,000** and executes:

```sql
SET SESSION mhnsw_ef_search = %s
```

Session scope prevents changing the global server setting or another connection's setting. Integration tests verify valid and invalid values, persistence within one connection, connection isolation, and unchanged global settings. A systematic real-corpus `ef_search` sweep remains a possible extension.

## 7. Verification evidence: early milestones and real corpus

### 7.1 Historical database-development tests

The early database implementation was tested before Wikipedia ingestion. At one point, `sql/002_example_queries.sql` **Q1–Q5 executed without SQL errors** while the application database had:

| Historical measurement | Count |
| --- | ---: |
| Articles | 0 |
| Chunks | 0 |
| Resolved links | 0 |

That run established SQL syntax acceptance, **not correctness of results over populated Wikipedia tables**. 
The SQL demonstrations were subsequently updated to select real
Computer Science corpus parameters automatically. On 13 November 2026,
Q1–Q5 executed successfully against the populated application database
and returned matching Wikipedia results, including semantic rankings,
topic and category filtering, resolved article links, and combined
relational constraints.


Other earlier milestones recorded **278 passing tests (183 unit, 95 integration)** and later **296 passing tests (191 unit, 105 integration)**. Those are retained only as development history; they are **not current test totals**. The larger project suite subsequently expanded to ingestion, retrieval, evaluation, database experiments, CLI, and end-to-end coverage. The full suite passed locally before the latest documentation changes; rerun `make test` for the exact current count.

### 7.2 Controlled MariaDB integration evidence

The integration suite verifies:

- Creation and inspection of the `VECTOR(384)` column and cosine HNSW index.
- Vector insertion through `VEC_FromText` and round-trip decoding through `VEC_ToText`.
- Atomic insert, update, skip, deletion, and rollback across related tables.
- Category, topic, date, length, include/exclude ID, link, and distance filters.
- Correct filtering **before** exact top-K ranking, including a selective-category test with closer nonmatching chunks.
- Consistent behavior between `WikiRepository` and `InMemoryRepository` on controlled cases.
- Index selection for semantic retrieval and index exclusion for exact retrieval via `EXPLAIN`.
- Session-scoped HNSW settings and incompatible embedding-metadata rejection.

A separate controlled example used Physics and Biology category records to show correct selective filtering. These were **synthetic test records**, not the production corpus topics.

### 7.3 Real Wikipedia retrieval evaluation

The team subsequently ingested **200 real Wikipedia articles with 8,743 chunks** and evaluated a frozen labeled dataset of **40 questions**. The published benchmark reports were generated with one warm-up and five measured repetitions per query. Article IDs were deduplicated before calculating retrieval metrics.

| Evaluated setting | Questions | MRR | Recall@5 | Recall@10 | P50 retrieval latency |
| --- | ---: | ---: | ---: | ---: | ---: |
| Full semantic evaluation | 40 | 0.8644 | 0.9500 | 1.0000 | 6.50 ms |
| Semantic on constrained subset | 15 | 0.7551 | 0.8667 | 1.0000 | 6.16 ms |
| Hybrid on the same subset | 15 | 0.7583 | 0.8667 | 1.0000 | 563.56 ms |

For the constrained subset, hybrid results satisfied the tested relational predicates; the team also measured compliance independently against stored article metadata. These latency numbers describe the **recorded benchmark environment and workload**; results will differ across machines. The hybrid baseline favors correctness under filters and can be much slower than indexed semantic search.

See [Evaluation](evaluation.md), [`evaluation_semantic.md`](../reports/evaluation_semantic.md), [`evaluation_comparison.md`](../reports/evaluation_comparison.md), and [`evaluation_metadata.json`](../reports/evaluation_metadata.json). Retrieval metrics **do not** measure the factual correctness of the extractive RAG answer.

## 8. MariaDB depth experiments

The project contains three separate experiments described in [Database Experiments](database_experiments.md).

| Experiment | Data / setup | Verified observation |
| --- | --- | --- |
| C: Metric mismatch | 8,743 real Wikipedia vectors | Direct cosine expression used the `embedding` index; Euclidean and wrapped-cosine expressions did not in the measured execution plans |
| D: Transaction visibility | Isolated `wikirag_test` | Uncommitted vector rows remained invisible; commit, rollback, and cleanup were verified under `READ COMMITTED` and `REPEATABLE READ` |
| E: HNSW cache size | Isolated synthetic corpus of 6,000 vectors | Cache size affected measured latency; the five-cycle benchmark is synthetic and cannot establish Wikipedia-scale performance |

The real-corpus metric-mismatch report recorded mean latencies of **2.846 ms** for direct indexed cosine, **1,465.732 ms** for Euclidean, and **1,689.556 ms** for wrapped cosine in its particular WSL/Docker run. These are measured examples of index-plan sensitivity, **not universal speedup claims**.

Raw reports:

- [`metric_mismatch_wikipedia.json`](../results/experiments/metric_mismatch_wikipedia.json)
- [`transaction_visibility_wikirag.json`](../results/experiments/transaction_visibility_wikirag.json)
- [`cache_size_synthetic.json`](../results/experiments/cache_size_synthetic.json)

The cache experiment runs in a **separate Docker service and database** (`wikirag_cache_test`, host port `13308`). Its reproducibility and cold-cache caveats are documented with the results. Additional benchmark sweeps for HNSW search breadth, filter selectivity, and chunk-size sensitivity remain possible improvements.

## 9. SQL demonstrations

[`sql/002_example_queries.sql`](../sql/002_example_queries.sql) contains six Area 4 examples:

| Query | Demonstration |
| --- | --- |
| Q1 | Indexed semantic top-K retrieval |
| Q2 | Cosine ranking constrained by topic |
| Q3 | Category membership through relational joins |
| Q4 | Semantic results expanded through outgoing Wikipedia links |
| Q5 | Combined category, article length, revision date, and link filters |
| Q6 | Two-session transaction-visibility scenario, intentionally commented out |


**Populated-corpus verification (13 November 2026):** Q1–Q5 executed
successfully against the ingested Wikipedia corpus. The script selected
Ada Lovelace as a source article and Artificial intelligence as a
linked target. All five demonstrations returned results, including
Q5 with category, length, revision-date, and link predicates combined.

The Q5 threshold values are selected from a known matching target
article, so this demonstrates the correctness of combined predicates
rather than measuring filter selectivity or query performance.


After checking example values, execute the read-only Q1–Q5 statements from the repository root with:

```bash
docker compose exec -T db sh -c \
  'MYSQL_PWD="$MARIADB_PASSWORD" mariadb -u "$MARIADB_USER" "$MARIADB_DATABASE"' \
  < sql/002_example_queries.sql
```

Q6 is a two-session teaching example and must **not** be run as an uncontrolled write against the main database. The automated transaction-visibility experiment uses the isolated test database instead.

## 10. Test isolation, CI, and maintenance

The three databases serve different purposes:

| Database | Purpose | Safety policy |
| --- | --- | --- |
| `wikirag` | Main Wikipedia corpus and normal CLI demo | Never recreated by routine tests or experiments |
| `wikirag_test` | MariaDB integration and end-to-end tests | Tests may recreate the schema after checking the safe `_test` name |
| `wikirag_cache_test` | Synthetic HNSW cache-size experiments | Separate container, port, and persistent volume |

`db/schema.py::init_schema(recreate=True)` refuses to operate unless the selected database matches the configured test database and ends with `_test`. The CLI and experiment code also validate test-database separation. Database integration and end-to-end tests can modify `wikirag_test`, so **do not use it for irreplaceable data**.

Before proposing or merging database changes:

```bash
uv lock --check
make test
make lint
git diff --check
```

The GitHub Actions configuration runs unit checks and a separate MariaDB job with both `integration` and `e2e` tests. A local green suite does **not** by itself prove that the final pull-request CI checks passed; inspect GitHub after opening the PR.

Keep the following synchronized during future changes:

- `sql/001_schema.sql`, `verify_schema()`, repository SQL, and the schema documentation.
- The embedding-model configuration, the 384-dimensional vector contract, and `embedding_meta`.
- Shared method signatures in [`interfaces.md`](interfaces.md), including fake-versus-real repository behavior.
- README commands, demo requirements, dataset metadata, experimental conditions, and committed benchmark reports.
- Database isolation safeguards and the rule that completed work must be merged into **`main`** for the official evaluation.

## 11. Limitations and future work

- The chosen corpus contains 200 Wikipedia articles rather than Wikipedia at full scale.
- Full semantic retrieval uses an HNSW-eligible query, while filtered hybrid retrieval intentionally uses **exact** cosine ranking. Do not call the filtered path HNSW-accelerated.
- A 40-question curated ground truth may not generalize to arbitrary user questions. It evaluates retrieval, not the correctness of the generated text.
- The controlled four-vector HNSW-versus-exact comparison is not a real-corpus approximate-recall study.
- The measured latency and index plans depend on MariaDB version, host hardware, workload, query shape, and configuration.
- The synthetic cache results do not establish an optimal production cache size.

For the full end-to-end data flow and how this database layer connects to ingestion, retrieval, RAG, evaluation, and the CLI, read [System Architecture](architecture.md).
