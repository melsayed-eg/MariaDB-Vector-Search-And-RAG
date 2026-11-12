A project for area 4, "Vector search and RAG, natively" for the [MariaDB student database projects, 2026-09](https://mariadb.org/bachelor_hackathon_2026-09/).

# MariaDB WikiRAG

## 1. Project Overview

WikiRAG is a Wikipedia retrieval and retrieval-augmented generation (RAG) project built using **MariaDB 11.8** and its native vector search capabilities.

The project aims to combine:

- Semantic search using vector embeddings.
- Relational SQL filtering and joins.
- Native MariaDB vector indexing.
- Transactionally consistent storage.
- Retrieval-augmented generation.
- Evaluation using recall and latency measurements.

Unlike an architecture that requires a separate vector database, WikiRAG aims to store article metadata and embeddings together in MariaDB.

**Current status:** Core database, ingestion, retrieval, RAG, and evaluation components are implemented. Final evaluation review and verification remain in progress.

---

## 2. Technology Stack

| Component | Technology |
|-----------|------------|
| Programming language | Python |
| Database | MariaDB 11.8 |
| Vector storage | MariaDB native VECTOR |
| Vector indexing | HNSW |
| Embedding model | sentence-transformers/all-MiniLM-L6-v2 |
| Embedding dimensions | 384 |
| Dependency management | uv |
| Database environment | Docker Compose |
| Unit testing | pytest |
| Code quality | Ruff |
| Version control | Git and GitHub |

---

## 3. Prerequisites

Before installing the project, ensure you have:

- Git
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- Docker and Docker Compose
- Internet access for the initial dependency and embedding-model downloads

The foundation and CPU-only embedding installation have been tested using **Python 3.14.4 on WSL Ubuntu**.

The project's supported Python versions are declared in `pyproject.toml`.

---

## 4. Installation

### Step 1: Clone the Repository

```bash
git clone https://github.com/melsayed-eg/MariaDB-Vector-Search-And-RAG.git

cd MariaDB-Vector-Search-And-RAG
```

### Step 2: Install Project Dependencies

Run:

```bash
uv sync --extra dev --extra embeddings --locked
```

This command:

1. Creates or updates the project's `.venv` virtual environment.
2. Installs the required Python dependencies.
3. Installs development tools such as pytest and Ruff.
4. Installs Sentence Transformers and CPU-only PyTorch.
5. Uses the dependency versions recorded in `uv.lock`.

**An NVIDIA GPU is not required.**

The CPU-only PyTorch package source is configured in `pyproject.toml`, so contributors do not need to install PyTorch separately.

### Step 3: Activate the Virtual Environment

On Linux or WSL Ubuntu:

```bash
source .venv/bin/activate
```

Alternatively, use `uv run` to execute project commands without manually activating the virtual environment.

---

## 5. Environment Configuration

Copy the example environment file:

```bash
cp .env.example .env
```

Edit `.env` and replace the example passwords with your own local credentials.

The configuration includes:

- MariaDB connection settings.
- Application database name.
- Test database name.
- Embedding model.
- Logging settings.
- Optional LLM configuration.

**Security:** Never commit `.env`, passwords, API keys, or other credentials to GitHub.

---

## 6. Starting MariaDB

The project uses MariaDB 11.8 through Docker Compose.

Start the database:

```bash
docker compose up -d
```

Check the running containers:

```bash
docker compose ps
```

Stop the database:

```bash
docker compose down
```

The default development configuration exposes MariaDB on:

```text
Host: 127.0.0.1
Port: 13307
```

See the project documentation and Makefile for database initialization, test setup, and Wikipedia ingestion workflows.

---

## 7. Running Tests

### Run Unit Tests

```bash
uv run --extra dev --extra embeddings python -m pytest -m unit -q
```

The project includes unit, integration, and evaluation tests. Run the full suite to verify the current test count.

These tests cover the implemented shared foundation components, including:

- Shared data models.
- Configuration validation.
- Custom exceptions.
- Fake embedding and repository implementations.
- Repository hygiene checks.

### Run Ruff Linting

```bash
uv run --extra dev ruff check .
```

### Check Code Formatting

```bash
uv run --extra dev ruff format --check .
```

Integration and end-to-end tests are included where implemented; some require a running MariaDB instance.

---

## 8. Embedding Model

WikiRAG uses the following embedding model:

```text
sentence-transformers/all-MiniLM-L6-v2
```

The model converts text into a **384-dimensional numerical vector**.

These vectors will be stored using MariaDB's native `VECTOR(384)` type.

The project's default installation uses CPU-only PyTorch.

### Verify the Embedding Model

After installation, run:

```bash
uv run --extra embeddings python -c "from sentence_transformers import SentenceTransformer; model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2', device='cpu'); vector = model.encode('MariaDB supports vector search.'); print('Embedding dimensions:', vector.shape); assert vector.shape == (384,)"
```

Expected output:

```text
Embedding dimensions: (384,)
```

The initial execution may download the model weights.

---

## 9. Dependency Management

The project uses **uv** for Python dependency and environment management.

Two files control dependency installation:

### `pyproject.toml`

Defines the project's direct dependencies, optional dependency groups, and package-source configuration.

### `uv.lock`

Records resolved dependency versions and package information to support reproducible installation.

The project configures CPU-only PyTorch rather than requiring NVIDIA CUDA libraries.

The previously used `requirements.lock` was an environment-specific package snapshot and has been replaced by the uv-based dependency management approach.

When installing the project, use:

```bash
uv sync --extra dev --extra embeddings --locked
```

Do not manually install individual dependencies unless you are intentionally changing the project's dependency configuration.

---

## 10. Project Architecture

The application is organized into separate components.

| Component | Responsibility |
|-----------|----------------|
| Database | MariaDB connections, schema, transactions, and vector search |
| Ingestion | Wikipedia collection, cleaning, chunking, and embedding |
| Retrieval | Semantic search and relational filtering |
| RAG | Building context and generating grounded responses |
| Evaluation | Measuring retrieval quality and query latency |

The shared interfaces are defined in:

[docs/interfaces.md](docs/interfaces.md)

---

## 11. Development Workflow

Contributors work on feature branches and submit pull requests for review.

Before submitting changes:

1. Run the relevant tests.
2. Run Ruff linting and formatting checks.
3. Update documentation where necessary.
4. Review the Git diff.
5. Commit tested changes.
6. Push the feature branch and open a pull request.

The `main` branch should contain reviewed, runnable work.

See [CONTRIBUTING.md](CONTRIBUTING.md) for the detailed Git workflow and contribution guidelines.

---

## 12. Team Responsibilities

| Area | Responsibility |
|------|----------------|
| Database and integration contributor | MariaDB schema, repository implementation, native vector search, SQL filtering, and integration tests |
| Zineb | Wikipedia collection, text cleaning, chunking, embeddings, and ingestion |
| Marwan | Retrieval, RAG pipeline, evaluation, and experiments |

All contributors participate in reviewing shared interfaces, integration decisions, and pull requests.

---

## 13. Retrieval Evaluation

WikiRAG includes a reproducible evaluation workflow using MariaDB 11.8,
the Wikipedia corpus, and the MiniLM embedding model.

The evaluation dataset contains 40 questions: 25 semantic questions and
15 constrained questions. The benchmark evaluates all 40 questions in
semantic mode and compares semantic and hybrid retrieval on the same
15 constrained questions.

Run the benchmark against the populated local database:

    make eval

The benchmark requires 200 articles and 8,743 embedded chunks.
It measures Recall@K, Precision@K, MRR, and retrieval latency, verifies
hybrid SQL filter compliance, and regenerates the evaluation reports.

Results and methodology:

- [Evaluation Methodology](docs/evaluation.md)
- [Semantic Evaluation](reports/evaluation_semantic.md)
- [Semantic/Hybrid Comparison](reports/evaluation_comparison.md)
- [Reproducibility Metadata](reports/evaluation_metadata.json)

Hybrid retrieval uses exact cosine ranking with relational SQL filters,
whereas semantic retrieval uses the HNSW index. Their latency differences
therefore cannot be attributed solely to filtering.

Relevance judgments remain provisional pending independent review.

---

## 14. Current Development Status

### Implemented

- Python packaging, configuration, and shared interfaces.
- MariaDB schema, repository, native VECTOR storage, and HNSW indexing.
- Wikipedia ingestion, chunking, and embeddings.
- Semantic and SQL-constrained hybrid retrieval.
- RAG pipeline components.
- Retrieval evaluation and automated filter-compliance checks.
- Reproducible benchmark reports and environment metadata.
- Unit and database integration testing infrastructure.

### Remaining Verification

- Final independent review of evaluation relevance judgments.
- Final verification after any subsequent code or dataset changes.
- Regeneration and approval of final evaluation reports.
- Additional experiments and production-scale validation.

---

## 15. Additional Documentation

- [Shared Interfaces](docs/interfaces.md)
- [Contribution Guidelines](CONTRIBUTING.md)
- [MariaDB Project Assignment](https://mariadb.org/bachelor_hackathon_2026-09/)
- [MariaDB Documentation](https://mariadb.com/docs/)
- [uv Documentation](https://docs.astral.sh/uv/)

### Database depth experiments

The MariaDB database layer has been evaluated using controlled
synthetic vector experiments on MariaDB 11.8.9.

- **Metric mismatch:** Direct cosine ranking used the native
  HNSW index; modified distance expressions did not select it
  in the controlled verification.
- **Transaction visibility:** Relational records and indexed
  vectors were visible together after commit, but not before.
  A deletion-related HNSW regression was reproduced and mitigated.
- **HNSW cache size:** Three cache limits were compared using
  five restart cycles and 125 warm measurements per setting.

| Cache limit | Mean latency | p95 latency |
| --- | ---: | ---: |
| 1 MiB | 6.018 ms | 8.516 ms |
| 16 MiB | 2.878 ms | 5.023 ms |
| 64 MiB | 3.016 ms | 4.683 ms |

The measurements use 6,000 synthetic VECTOR(384) embeddings.
They do not establish retrieval quality or optimal settings
for the final Wikipedia corpus.

Full methodology and reproduction instructions:
[Database Depth Experiments](docs/database_experiments.md).

Machine-readable results:
[HNSW Cache Benchmark](results/experiments/cache_size_synthetic.json).
