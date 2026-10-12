
# Database Access Layer (DAL) API Reference

## Overview

The Data Access Layer (DAL) provides Python functions for interacting with the MariaDB database.

It handles:
- Wikipedia article storage and retrieval
- Text chunks and vector embeddings
- Article categories
- Links between Wikipedia articles
- Native vector similarity search
- Transactional ingestion

The DAL is located in `src/database/`.

All examples assume Python is running from the project environment with database credentials configured in `.env`.

## 1. Database Connection

**File:** `src/database/connection.py`

### `get_connection()`

Creates and returns a PyMySQL connection to MariaDB.

```python
from src.database.connection import get_connection

connection = get_connection()
try:
    print("Connected to MariaDB")
finally:
    connection.close()
```

Connection settings are loaded from `.env`.

## 2. Article Operations

**File:** `src/database/articles.py`

### `upsert_article(article, connection=None)`

Inserts a new article or updates an existing article with the same `article_id`.

Expected article dictionary:

```python
article = {
    "article_id": 12345,
    "title": "Artificial intelligence",
    "url": "https://en.wikipedia.org/wiki/Artificial_intelligence",
    "content": "Article text goes here...",
    "last_edited": "2026-10-01 12:00:00"
}
```

Example:

```python
from src.database.articles import upsert_article

upsert_article(article)
```

The function calculates `length_bytes` from the UTF-8 encoded article content.

### `get_article(article_id, connection=None)`

Retrieves an article by its Wikipedia article ID.

```python
from src.database.articles import get_article

article = get_article(12345)
```

Returns an article dictionary or `None` if the article does not exist.

### `delete_article(article_id, connection=None)`

Deletes an article by ID.

```python
from src.database.articles import delete_article

deleted_count = delete_article(12345)
```

Returns the number of deleted article rows.

Associated chunks, category assignments, and article links are removed automatically through foreign key cascading.

## 3. Chunk and Embedding Operations

**File:** `src/database/chunks.py`

### `insert_chunks(article_id, chunks, connection=None)`

Inserts text chunks and their vector embeddings.

Example:

```python
from src.database.chunks import insert_chunks

chunks = [
    {
        "chunk_index": 0,
        "chunk_text": "Artificial intelligence is...",
        "embedding": [0.1] * 384
    },
    {
        "chunk_index": 1,
        "chunk_text": "Machine learning is...",
        "embedding": [0.2] * 384
    }
]

inserted_count = insert_chunks(12345, chunks)
```

Each embedding must contain exactly 384 finite numerical values.

The referenced article must already exist.

Returns the number of inserted chunks.

### `get_chunks_by_article(article_id, connection=None)`

Retrieves an article's chunks in ascending `chunk_index` order.

```python
from src.database.chunks import get_chunks_by_article

chunks = get_chunks_by_article(12345)
```

Returns a collection of dictionaries containing:
- `chunk_id`
- `article_id`
- `chunk_index`
- `chunk_text`

This function does not return the embedding vectors.

### `replace_article_chunks(article_id, chunks, connection=None)`

Deletes an article's existing chunks and inserts the supplied replacements.

```python
from src.database.chunks import replace_article_chunks

replace_article_chunks(12345, new_chunks)
```

Useful when an article is reprocessed or its embeddings are regenerated.

Returns the number of newly inserted chunks.

## 4. Category Operations

**File:** `src/database/categories.py`

### `set_article_categories(article_id, category_names, connection=None)`

Replaces the category assignments for an article.

```python
from src.database.categories import set_article_categories

set_article_categories(
    12345,
    ["Computer science", "Artificial intelligence"]
)
```

The function:
1. Removes previous category assignments.
2. Reuses existing category records or creates new ones.
3. Associates the article with the supplied categories.
4. Avoids duplicate category names within the supplied list.

The article must already exist.

## 5. Article Link Operations

**File:** `src/database/links.py`

### `set_article_links(source_id, target_ids, connection=None)`

Replaces the outgoing links of a Wikipedia article.

```python
from src.database.links import set_article_links

set_article_links(
    12345,
    [67890, 11111]
)
```

This records links from article `12345` to the two target articles.

All referenced target articles must already exist in the database.

Returns the number of unique target IDs supplied.

**Important for ingestion:** When importing many articles, insert the article records first. Add links afterward, once their target articles exist.

Only store links to articles included in the database corpus.

## 6. Native Vector and Hybrid Search

**File:** `src/database/search.py`

### `search_chunks(...)`

Finds chunks ranked by cosine distance to a query embedding.

Function signature:

```python
search_chunks(
    query_embedding,
    limit=5,
    category=None,
    edited_after=None,
    min_length=None,
    linked_from=None,
    connection=None
)
```

### Parameters

| Parameter | Description |
|---|---|
| `query_embedding` | A 384-dimensional query vector |
| `limit` | Maximum number of returned chunks |
| `category` | Optional exact category-name filter |
| `edited_after` | Optional lower bound for article edit time (exclusive) |
| `min_length` | Optional minimum article length in UTF-8 bytes |
| `linked_from` | Optional source article ID whose outgoing links restrict results |
| `connection` | Optional existing MariaDB connection |

Example:

```python
from src.database.search import search_chunks

query_embedding = [0.1] * 384

results = search_chunks(
    query_embedding=query_embedding,
    limit=5,
    category="Computer science",
    min_length=1000
)

for result in results:
    print(result["title"], result["distance"])
```

The function returns chunk records with:
- `chunk_id`
- `article_id`
- `chunk_index`
- `chunk_text`
- `title`
- `url`
- `length_bytes`
- `last_edited`
- `distance`

Lower cosine distance means greater similarity.

The query combines MariaDB's native `VEC_DISTANCE_COSINE()` function with ordinary SQL joins and filters.

**For the RAG teammate:** Generate the query embedding using the same embedding model and dimensionality used during ingestion.

## 7. Transactional Article Ingestion

**File:** `src/database/ingestion.py`

### `save_article_with_metadata(...)`

Saves an article and its related data in a single transaction.

Function signature:

```python
save_article_with_metadata(
    article,
    chunks,
    categories,
    links,
    connection=None
)
```

Example:

```python
from src.database.ingestion import save_article_with_metadata

article = {
    "article_id": 12345,
    "title": "Artificial intelligence",
    "url": "https://en.wikipedia.org/wiki/Artificial_intelligence",
    "content": "Article text goes here...",
    "last_edited": "2026-10-01 12:00:00"
}

chunks = [
    {
        "chunk_index": 0,
        "chunk_text": "Article text goes here...",
        "embedding": [0.1] * 384
    }
]

saved_id = save_article_with_metadata(
    article=article,
    chunks=chunks,
    categories=["Computer science"],
    links=[]
)

print(saved_id)
```

The function calls:
1. `upsert_article()`
2. `replace_article_chunks()`
3. `set_article_categories()`
4. `set_article_links()`

When it creates its own database connection, it commits only after all operations succeed.

If an operation fails, it rolls back the transaction.

Returns the article ID.

## 8. Connection and Transaction Management

Most DAL functions accept an optional `connection` parameter.

### Without an existing connection

```python
upsert_article(article)
```

The function creates its own connection and manages its transaction when applicable.

### With an existing connection

```python
from src.database.connection import get_connection
from src.database.articles import upsert_article
from src.database.categories import set_article_categories

connection = get_connection()

try:
    upsert_article(article, connection=connection)
    set_article_categories(
        article["article_id"],
        ["Computer science"],
        connection=connection
    )
    connection.commit()
except Exception:
    connection.rollback()
    raise
finally:
    connection.close()
```

When a connection is supplied, the caller is responsible for committing, rolling back, and closing it.

This allows multiple DAL operations to participate in one transaction.

## 9. Recommended Integration Workflow

### Wikipedia ingestion teammate

1. Fetch Wikipedia articles and metadata.
2. Split article text into chunks.
3. Generate 384-dimensional embeddings.
4. Call `save_article_with_metadata()` with `links=[]`.
5. After all article records exist, call `set_article_links()` for links to articles in the corpus.

### RAG teammate

1. Receive a user question.
2. Generate its embedding using the ingestion embedding model.
3. Call `search_chunks()` with optional SQL filters.
4. Use the returned chunk text as retrieval context.
5. Pass that context to the answer-generation component.

## 10. Testing

Run the DAL integration tests:

```bash
python -m pytest tests/ -v
```

Tests should be run against a local development database.

The tests cover article operations, chunk storage, vector validation, category and link relationships, hybrid search filters, and transaction rollback.
