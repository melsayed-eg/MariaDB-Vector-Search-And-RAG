import json
import math

from .connection import get_connection


def insert_chunks(article_id, chunks, connection=None):
    # Validate all chunks before inserting anything.
    prepared_values = []

    for chunk in chunks:
        embedding = chunk["embedding"]

        # Our embedding model produces exactly 384 numbers.
        if len(embedding) != 384:
            raise ValueError("Embedding must contain exactly 384 dimensions")

        # Ensure every embedding value is a finite number.
        if any(
            isinstance(value, (bool, str, bytes))
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            for value in embedding
        ):
            raise ValueError("Embedding must contain only finite numbers")

        # Convert the Python list into JSON text for MariaDB.
        embedding_text = json.dumps(embedding)

        prepared_values.append((
            article_id,
            chunk["chunk_index"],
            chunk["chunk_text"],
            embedding_text
        ))

    # Nothing to insert if the list is empty.
    if not prepared_values:
        return 0

    own_connection = connection is None

    if own_connection:
        connection = get_connection()

    try:
        sql = """
            INSERT INTO chunks (
                article_id,
                chunk_index,
                chunk_text,
                embedding
            )
            VALUES (%s, %s, %s, VEC_FromText(%s))
        """

        with connection.cursor() as cursor:
            cursor.executemany(sql, prepared_values)
            inserted_count = cursor.rowcount

        if own_connection:
            connection.commit()

        return inserted_count

    except Exception:
        if own_connection:
            connection.rollback()
        raise

    finally:
        if own_connection:
            connection.close()


def get_chunks_by_article(article_id, connection=None):
    # Check whether the function needs to create its own connection.
    own_connection = connection is None

    # Create a new connection only if one was not provided.
    if own_connection:
        connection = get_connection()

    try:
        # Retrieve all chunks belonging to the specified article.
        # ORDER BY ensures chunks are returned in their original order.
        sql = """
            SELECT
                chunk_id,
                article_id,
                chunk_index,
                chunk_text
            FROM chunks
            WHERE article_id = %s
            ORDER BY chunk_index
        """

        # Execute the query safely using a parameterized statement.
        with connection.cursor() as cursor:
            cursor.execute(sql, (article_id,))

            # fetchall() returns all matching chunks.
            chunks = cursor.fetchall()

        # Return the chunks as a list of dictionaries.
        return chunks

    finally:
        # Close the connection only if this function created it.
        # An externally provided connection must remain open.
        if own_connection:
            connection.close()


def replace_article_chunks(article_id, chunks, connection=None):
    # Check whether the function needs to create its own connection.
    own_connection = connection is None

    # Create a new connection only if one was not provided.
    if own_connection:
        connection = get_connection()

    try:
        # Delete all existing chunks belonging to this article.
        sql = """
            DELETE FROM chunks
            WHERE article_id = %s
        """

        # Execute the DELETE query using a parameterized statement.
        with connection.cursor() as cursor:
            cursor.execute(sql, (article_id,))

        # Insert the new chunks using our existing DAL function.
        # Pass the same connection so both operations share a transaction.
        inserted_count = insert_chunks(
            article_id,
            chunks,
            connection=connection
        )

        # Commit both the deletion and insertion together,
        # but only if this function created the connection.
        if own_connection:
            connection.commit()

        # Return the number of newly inserted chunks.
        return inserted_count

    except Exception:
        # If anything fails, undo both operations.
        # This preserves the original chunks.
        if own_connection:
            connection.rollback()
        raise

    finally:
        # Close only connections created by this function.
        if own_connection:
            connection.close()