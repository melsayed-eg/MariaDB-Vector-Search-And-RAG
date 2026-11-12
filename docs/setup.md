
# WikiRAG — Automated Setup and Reproduction

## Prerequisites

Install the following tools:

- Git
- uv
- Docker with Docker Compose
- GNU Make
- Internet access for initial dependencies and embedding model downloads

The project has been developed using Python 3.14.4 in Ubuntu WSL.

Python requirements are recorded in pyproject.toml and uv.lock.

## Fresh-Clone Setup

Clone the repository:

```bash
git clone https://github.com/melsayed-eg/MariaDB-Vector-Search-And-RAG.git
cd MariaDB-Vector-Search-And-RAG
```

Create the local environment file:

```bash
cp .env.example .env
```

Edit `.env` and configure local database credentials.

Do not commit `.env`, passwords, or API keys.

Run:

```bash
make setup
```

This command:

1. Installs locked dependencies with uv, including CPU embeddings.
2. Starts the main MariaDB 11.8 Docker service and waits for health checks.
3. Initializes or verifies the canonical MariaDB schema.
4. Ingests the committed Wikipedia JSONL snapshot.
5. Creates or verifies the separate integration-test database.
6. Prints the article, chunk, topic, and category counts.

The committed corpus is expected to produce 200 Wikipedia articles
and 8,743 embedded chunks with the project's documented settings.

The initial ingestion requires the embedding model and may need
an internet connection to download model weights.

## Re-running Setup

The setup command is designed to be repeatable.

It does not delete Docker volumes or recreate the application schema.

The ingestion pipeline uses deterministic article fingerprints.
Articles with unchanged content and settings are skipped.

If a snapshot, chunking configuration, or embedding model changes,
the ingestion behavior may differ.

## Useful Commands

Start the database:

```bash
make up
```

Check the MariaDB version:

```bash
make version
```

Display stored corpus statistics:

```bash
uv run python -m wikirag.cli stats
```

Run unit tests:

```bash
make test-unit
```

Run database integration tests:

```bash
make test-db
```

Run linting and formatting checks:

```bash
make lint
```

Regenerate retrieval evaluation reports:

```bash
make eval
```

Note that `make eval` overwrites the generated evaluation report
files. Review report changes before committing them.

Stop the main database container:

```bash
make down
```

This does not delete its named data volume.

## Database Isolation

The databases have different purposes:

- `wikirag`: Main Wikipedia application corpus, normally port 13307.
- `wikirag_test`: Dedicated database for integration tests.
- `wikirag_cache_test`: Synthetic HNSW cache experiment database,
  exposed separately on port 13308.

Do not reset the main database to run an experiment.

The separate cache experiment uses docker-compose.cache.yml and
its own persistent volume.

## Troubleshooting

### Missing .env

Create `.env` from `.env.example` and configure credentials.

### Docker not running

Start Docker Desktop or the local Docker service, and ensure
Docker Compose is accessible from your terminal.

### Database schema mismatch

Do not delete tables automatically. Review the schema mismatch
and the canonical SQL definition before making changes.

### Ingestion skips all articles

This is expected when the same committed snapshot has already
been ingested with unchanged chunk and embedding settings.

### Orphan cache-db warning

Docker Compose may report the separate cache-db container as
an orphan when starting the main database. Do not use
`--remove-orphans` during normal setup.

### Unexpected corpus counts

Inspect the ingestion results and configuration. Do not reset
the database solely because the counts differ.
