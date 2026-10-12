
import math

import pytest
import pymysql

from src.database.connection import get_connection
from src.database.articles import upsert_article, get_article
from src.database.chunks import insert_chunks, get_chunks_by_article
from src.database.categories import set_article_categories
from src.database.links import set_article_links
from src.database.search import search_chunks
from src.database.ingestion import save_article_with_metadata


# Reserved negative IDs for these tests.
A = -910001
B = -910002
C = -910003


@pytest.fixture
def db():
    connection = get_connection()
    try:
        yield connection
    finally:
        connection.rollback()
        connection.close()


def article(article_id, title, content="Test content"):
    return {
        "article_id": article_id,
        "title": title,
        "url": f"https://example.com/{article_id}",
        "content": content,
        "last_edited": "2026-10-01 12:00:00",
    }


def vector(x=0.0, y=0.0):
    return [float(x), float(y)] + [0.0] * 382


def chunk(index, text, embedding):
    return {
        "chunk_index": index,
        "chunk_text": text,
        "embedding": embedding,
    }


def test_invalid_embedding_values(db):
    upsert_article(article(A, "Invalid Vectors"), connection=db)

    invalid_vectors = [
        [1.0, 2.0],                  # Wrong dimensions
        [float("nan")] * 384,        # NaN
        [float("inf")] * 384,        # Infinity
        ["hello"] * 384,             # Strings
        [True] * 384,                # Booleans
    ]

    for bad_vector in invalid_vectors:
        with pytest.raises(ValueError):
            insert_chunks(
                A,
                [chunk(0, "Invalid chunk", bad_vector)],
                connection=db,
            )

    assert len(get_chunks_by_article(A, connection=db)) == 0


def test_invalid_search_arguments():
    with pytest.raises(ValueError):
        search_chunks([1.0, 2.0])

    with pytest.raises(ValueError):
        search_chunks([float("nan")] * 384)

    with pytest.raises(ValueError):
        search_chunks(vector(1, 0), limit=0)

    with pytest.raises(ValueError):
        search_chunks(vector(1, 0), min_length=-1)


def test_category_replacement(db):
    upsert_article(article(A, "Categories"), connection=db)

    set_article_categories(
        A,
        ["Test Category Alpha", "Test Category Beta"],
        connection=db,
    )

    # Replacing categories should remove the old assignments.
    set_article_categories(
        A,
        ["Test Category Gamma"],
        connection=db,
    )

    with db.cursor() as cursor:
        cursor.execute(
            """
            SELECT c.name
            FROM article_categories ac
            JOIN categories c
                ON ac.category_id = c.category_id
            WHERE ac.article_id = %s
            """,
            (A,),
        )
        rows = cursor.fetchall()

    assert len(rows) == 1
    assert rows[0]["name"] == "Test Category Gamma"


def test_link_replacement(db):
    for article_id in (A, B, C):
        upsert_article(
            article(article_id, f"Article {article_id}"),
            connection=db,
        )

    set_article_links(A, [B, C], connection=db)

    # Replace two links with one.
    set_article_links(A, [C], connection=db)

    with db.cursor() as cursor:
        cursor.execute(
            """
            SELECT target_article_id
            FROM article_links
            WHERE source_article_id = %s
            """,
            (A,),
        )
        rows = cursor.fetchall()

    assert len(rows) == 1
    assert rows[0]["target_article_id"] == C


def test_foreign_key_violation(db):
    # Article A does not exist in this transaction.
    with pytest.raises(pymysql.err.IntegrityError):
        insert_chunks(
            A,
            [chunk(0, "Orphan chunk", vector(1, 0))],
            connection=db,
        )

    db.rollback()

    assert get_article(A, connection=db) is None


def test_combined_hybrid_filters(db):
    upsert_article(
        article(A, "Matching Article", "A" * 200),
        connection=db,
    )
    upsert_article(
        article(B, "Nonmatching Article", "B" * 50),
        connection=db,
    )
    upsert_article(
        article(C, "Source Article"),
        connection=db,
    )

    insert_chunks(
        A,
        [chunk(0, "Matching chunk", vector(1, 0))],
        connection=db,
    )
    insert_chunks(
        B,
        [chunk(0, "Other chunk", vector(0, 1))],
        connection=db,
    )

    set_article_categories(
        A,
        ["Test Hybrid Category"],
        connection=db,
    )
    set_article_categories(
        B,
        ["Other Category"],
        connection=db,
    )

    set_article_links(C, [A], connection=db)

    results = search_chunks(
        query_embedding=vector(1, 0),
        limit=5,
        category="Test Hybrid Category",
        edited_after="2026-09-01 00:00:00",
        min_length=100,
        linked_from=C,
        connection=db,
    )

    assert len(results) == 1
    assert results[0]["article_id"] == A

    # A stricter filter should eliminate the result.
    no_results = search_chunks(
        query_embedding=vector(1, 0),
        category="Test Hybrid Category",
        min_length=1000,
        linked_from=C,
        connection=db,
    )

    assert len(no_results) == 0


def test_failed_ingestion_rollback():
    """
    Test the ingestion function when it owns the connection.

    A missing link target should cause the entire operation
    to roll back automatically.
    """
    test_article = article(A, "Rollback Edge Case")

    with pytest.raises(pymysql.err.IntegrityError):
        save_article_with_metadata(
            article=test_article,
            chunks=[
                chunk(0, "Temporary chunk", vector(1, 0))
            ],
            categories=["Test Rollback Category"],
            links=[-999999998],
        )

    assert get_article(A) is None
