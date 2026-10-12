import pytest

from src.database.connection import get_connection
from src.database.articles import (
    upsert_article,
    get_article,
    delete_article,
)
from src.database.chunks import (
    insert_chunks,
    get_chunks_by_article,
    replace_article_chunks,
)
from src.database.categories import set_article_categories
from src.database.links import set_article_links
from src.database.search import search_chunks
from src.database.ingestion import save_article_with_metadata


# Reserved IDs for our integration tests.
SOURCE_ID = -900001
TARGET_ID = -900002
OTHER_ID = -900003

TEST_IDS = (SOURCE_ID, TARGET_ID, OTHER_ID)


def embedding(first=0.0, second=0.0):
    """Create a valid 384-dimensional embedding."""
    return [float(first), float(second)] + [0.0] * 382


def make_article(article_id, title, content="Test article content"):
    return {
        "article_id": article_id,
        "title": title,
        "url": f"https://example.com/wiki/{article_id}",
        "content": content,
        "last_edited": "2026-10-01 12:00:00",
    }


def make_chunk(index, text, vector):
    return {
        "chunk_index": index,
        "chunk_text": text,
        "embedding": vector,
    }


@pytest.fixture
def db():
    """
    Give each test a real MariaDB connection.

    Roll back the test's changes afterward so tests don't
    permanently modify the database.
    """
    connection = get_connection()

    try:
        yield connection
    finally:
        connection.rollback()
        connection.close()


def test_article_crud(db):
    article = make_article(SOURCE_ID, "Test Python")

    upsert_article(article, connection=db)

    saved = get_article(SOURCE_ID, connection=db)

    assert saved is not None
    assert saved["title"] == "Test Python"
    assert saved["length_bytes"] == len(article["content"].encode("utf-8"))

    article["title"] = "Updated Python"
    upsert_article(article, connection=db)

    updated = get_article(SOURCE_ID, connection=db)
    assert updated["title"] == "Updated Python"

    assert delete_article(SOURCE_ID, connection=db) == 1
    assert get_article(SOURCE_ID, connection=db) is None


def test_chunks(db):
    upsert_article(
        make_article(SOURCE_ID, "Chunk Test"),
        connection=db,
    )

    chunks = [
        make_chunk(0, "First chunk", embedding(1, 0)),
        make_chunk(1, "Second chunk", embedding(0, 1)),
    ]

    assert insert_chunks(SOURCE_ID, chunks, connection=db) == 2

    saved = get_chunks_by_article(SOURCE_ID, connection=db)

    assert len(saved) == 2
    assert saved[0]["chunk_text"] == "First chunk"
    assert saved[1]["chunk_index"] == 1

    replacement = [
        make_chunk(0, "Replacement chunk", embedding(1, 1))
    ]

    assert replace_article_chunks(
        SOURCE_ID,
        replacement,
        connection=db,
    ) == 1

    saved = get_chunks_by_article(SOURCE_ID, connection=db)

    assert len(saved) == 1
    assert saved[0]["chunk_text"] == "Replacement chunk"


def test_invalid_embedding(db):
    upsert_article(
        make_article(SOURCE_ID, "Invalid Embedding Test"),
        connection=db,
    )

    invalid_chunks = [
        make_chunk(0, "Bad chunk", [1.0, 2.0])
    ]

    with pytest.raises(ValueError):
        insert_chunks(
            SOURCE_ID,
            invalid_chunks,
            connection=db,
        )

    assert len(get_chunks_by_article(SOURCE_ID, connection=db)) == 0


def test_categories_and_links(db):
    upsert_article(
        make_article(SOURCE_ID, "Source"),
        connection=db,
    )
    upsert_article(
        make_article(TARGET_ID, "Target"),
        connection=db,
    )

    set_article_categories(
        SOURCE_ID,
        ["Integration Test Category", "Integration Test Category"],
        connection=db,
    )

    set_article_links(
        SOURCE_ID,
        [TARGET_ID, TARGET_ID],
        connection=db,
    )

    with db.cursor() as cursor:
        cursor.execute(
            """
            SELECT c.name
            FROM article_categories ac
            JOIN categories c ON c.category_id = ac.category_id
            WHERE ac.article_id = %s
            """,
            (SOURCE_ID,),
        )
        categories = cursor.fetchall()

        cursor.execute(
            """
            SELECT target_article_id
            FROM article_links
            WHERE source_article_id = %s
            """,
            (SOURCE_ID,),
        )
        links = cursor.fetchall()

    assert len(categories) == 1
    assert categories[0]["name"] == "Integration Test Category"

    assert len(links) == 1
    assert links[0]["target_article_id"] == TARGET_ID


def test_vector_search_and_filters(db):
    upsert_article(
        make_article(
            SOURCE_ID,
            "Machine Learning",
            content="A" * 200,
        ),
        connection=db,
    )

    upsert_article(
        make_article(
            TARGET_ID,
            "Operating Systems",
            content="B" * 50,
        ),
        connection=db,
    )

    upsert_article(
        make_article(
            OTHER_ID,
            "Linking Article",
        ),
        connection=db,
    )

    insert_chunks(
        SOURCE_ID,
        [make_chunk(0, "ML chunk", embedding(1, 0))],
        connection=db,
    )

    insert_chunks(
        TARGET_ID,
        [make_chunk(0, "OS chunk", embedding(0, 1))],
        connection=db,
    )

    set_article_categories(
        SOURCE_ID,
        ["Integration Test ML"],
        connection=db,
    )

    set_article_categories(
        TARGET_ID,
        ["Integration Test OS"],
        connection=db,
    )

    set_article_links(
        OTHER_ID,
        [SOURCE_ID],
        connection=db,
    )

    # Search without filters.
    results = search_chunks(
        embedding(1, 0),
        limit=2,
        connection=db,
    )

    assert results[0]["article_id"] == SOURCE_ID

    # Category filter.
    results = search_chunks(
        embedding(1, 0),
        category="Integration Test ML",
        connection=db,
    )

    assert any(r["article_id"] == SOURCE_ID for r in results)
    assert all(r["article_id"] == SOURCE_ID for r in results)

    # Minimum article length filter.
    results = search_chunks(
        embedding(1, 0),
        min_length=100,
        connection=db,
    )

    assert any(r["article_id"] == SOURCE_ID for r in results)
    assert all(r["length_bytes"] >= 100 for r in results)

    # Last-edited filter.
    results = search_chunks(
        embedding(1, 0),
        edited_after="2026-09-01 00:00:00",
        connection=db,
    )

    assert any(r["article_id"] == SOURCE_ID for r in results)

    # Wikipedia link filter.
    results = search_chunks(
        embedding(1, 0),
        linked_from=OTHER_ID,
        connection=db,
    )

    assert len(results) == 1
    assert results[0]["article_id"] == SOURCE_ID


def test_ingestion_transaction_rollback(db):
    article = make_article(SOURCE_ID, "Rollback Test")

    # This target doesn't exist, so the link insertion
    # should violate the foreign key constraint.
    nonexistent_target = -999999999

    with pytest.raises(Exception):
        save_article_with_metadata(
            article=article,
            chunks=[
                make_chunk(0, "Temporary chunk", embedding(1, 0))
            ],
            categories=["Rollback Test Category"],
            links=[nonexistent_target],
            connection=db,
        )

    # The caller owns this connection, so the caller
    # must explicitly roll back the failed transaction.
    db.rollback()

    assert get_article(SOURCE_ID, connection=db) is None