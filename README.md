
# Area 4 — Vector search and RAG, natively

This project is developed for the [MariaDB Student Database Projects Hackathon (2026-09)](https://mariadb.org/bachelor_hackathon_2026-09/).

## 1. Project Overview

This project aims to build a Wikipedia-based semantic search and Retrieval-Augmented Generation (RAG) system using MariaDB's native vector search capabilities.

Users will be able to ask natural-language questions, retrieve relevant Wikipedia passages, and generate answers grounded in the retrieved information.

The project will demonstrate how MariaDB combines vector similarity search with traditional relational queries in a single database.

## 2. Project Objectives

- Collect a reproducible dataset of Wikipedia articles.
- Split articles into smaller text chunks.
- Generate vector embeddings for each chunk.
- Store article metadata, chunks, and embeddings in MariaDB.
- Create a native MariaDB vector index.
- Retrieve relevant chunks using `VEC_DISTANCE_COSINE`.
- Combine semantic search with SQL filters and relational joins.
- Generate answers using retrieved Wikipedia passages.
- Evaluate retrieval quality and query latency.

## 3. Planned Architecture

### Data ingestion

Wikipedia → Text extraction → Chunking → Embeddings → MariaDB

### Question answering

User question → Question embedding → MariaDB vector search → Relevant chunks → Language model → Answer

## 4. Technology Stack

| Component | Technology |
|---|---|
| Database | MariaDB (version to be verified) |
| Programming language | Python |
| Dataset | Wikipedia |
| Vector storage and search | MariaDB native VECTOR and VECTOR INDEX |
| Embedding model | To be selected |
| RAG model | To be selected |
| User interface | To be selected |

## 5. Database Design

The database will store Wikipedia articles, their metadata, text chunks, and vector embeddings.

The schema will be documented once implemented, including table relationships, vector index configuration, and design decisions.

## 6. Project Structure

```text
MariaDB-Vector-Search-And-RAG/
├── README.md
├── pyproject.toml
├── .gitignore
├── .env.example
├── src/
│   ├── ingest/
│   ├── database/
│   ├── retrieval/
│   └── rag/
├── sql/
├── data/
├── evaluation/
├── app/
├── tests/
└── docs/
```

The directories shown above represent the planned structure and will be created during development.

## 7. Installation and Setup

To be documented after the development environment, database schema, and dependencies are finalized.

The final instructions will cover:

- Python environment setup
- MariaDB installation and configuration
- Environment variables
- Database schema initialization
- Wikipedia data collection
- Embedding generation
- Running the application

## 8. Hybrid Search

A central objective is to demonstrate MariaDB's ability to combine vector similarity search with relational SQL operations.

Planned examples include filtering search results by Wikipedia category, article length, or edit date, and joining retrieved chunks with article metadata.

The implemented SQL queries and example outputs will be documented here.

## 9. Evaluation

Retrieval will be evaluated using a ground-truth question set with known relevant Wikipedia source articles.

Planned measurements:

- Recall@5
- Query latency
- Retrieval results with and without SQL constraints

The final evaluation will document the dataset, methodology, results, and limitations.

## 10. Findings and Limitations

To be completed after implementation and evaluation.

## 11. Project Status

Initial repository setup in progress.
