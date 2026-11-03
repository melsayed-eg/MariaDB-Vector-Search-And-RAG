# Retrieval and RAG

## Retrieval behavior

`Retriever` embeds a user query and asks the repository to return ranked
chunk matches. It returns a `RetrievalResult` containing the query, selected
mode, effective filters, hits, and timing measurements.

- **Semantic retrieval** searches by the query embedding. Any supplied filters
  are deliberately ignored.
- **Hybrid retrieval** combines vector search with repository-supported
  filters. At least one active filter is required.

The retriever accepts `top_k` values from 1 through 100. Queries must be
non-empty strings, and the mode must be `semantic` or `hybrid`.

## Embedding compatibility

When a `Retriever` is constructed, it calls
`ensure_embedding_meta()` with the embedder's model name and vector dimension.
The repository is responsible for rejecting metadata incompatible with its
stored embeddings. This check fails early, before query retrieval.

## Timing measurements

`RetrievalResult` reports timings in milliseconds:

- `embed_ms`: time spent embedding the query.
- `search_ms`: time spent searching the repository.
- `latency_ms`: total time measured around embedding and search.

These timings help identify whether query embedding or repository search
dominates retrieval latency.

## Interfaces

The retriever currently declares narrow structural protocols named
`RetrieverEmbedder` and `RetrieverRepository`. They describe only the
operations needed by this component and are temporary until the shared
production interfaces are available. Coordinate any interface consolidation
with the team; do not independently change agreed shared signatures.

## Tests and database integration

Unit tests use `FakeEmbedder` and `InMemoryRepository` to exercise retrieval
without requiring a running database. They cover validation, timing fields,
filter behavior, returned hits, and embedding metadata incompatibility.

MariaDB integration tests verify native semantic search, hybrid filtering,
result ranking, and embedding metadata compatibility.

The RAG integration test uses one database article and a controlled embedder.
It verifies the connection between retrieval, MariaDB, context construction,
and cited answer generation. It does not measure Wikipedia ingestion,
production embedding quality, retrieval accuracy, or corpus-scale performance.

## RAG context and generation

`build_context()` preserves ranked hits, deduplicates chunk IDs, and assigns
numbered citations such as `[1]` and `[2]`. It respects the character limit
without splitting chunks and records when context is truncated.

`ExtractiveGenerator` is a deterministic, non-LLM baseline that selects
sentences from retrieved context and includes numbered source citations.

`answer_question()` connects retrieval, context construction, and generation.
It validates citations against available sources and returns a `RAGAnswer`.
When no usable sources are retrieved, it returns an insufficient-information
answer without calling the generator. Generator errors become `WikiRagError`.

## Verification

Run `uv run --no-sync pytest -v tests/integration/test_rag_pipeline.py`
to test the RAG-to-MariaDB connection using the isolated test database.
Run `uv run --no-sync pytest -q` for the complete test suite.
