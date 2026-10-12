import json
import math

from .connection import get_connection


def search_chunks(
    query_embedding,
    limit=5,
    category=None,
    edited_after=None,
    min_length=None,
    linked_from=None,
    connection=None
):
    # Validate the query embedding before sending it to MariaDB.
    if len(query_embedding) != 384:
        raise ValueError("Query embedding must contain exactly 384 dimensions")

    # Ensure every embedding value is a finite number.
    if any(
        isinstance(value, (bool, str, bytes))
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        for value in query_embedding
    ):
        raise ValueError("Query embedding must contain only finite numbers")

    # Validate the maximum number of results.
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("Limit must be a positive integer")

    # Validate the minimum article length, if supplied.
    if min_length is not None:
        if (
            isinstance(min_length, bool)
            or not isinstance(min_length, int)
            or min_length < 0
        ):
            raise ValueError("Minimum length must be a non-negative integer")

    # Convert the Python embedding list into JSON text.
    embedding_text = json.dumps(query_embedding)

    # Build the SQL query using MariaDB's native vector distance function.
    sql = """
        SELECT
            ch.chunk_id,
            ch.article_id,
            ch.chunk_index,
            ch.chunk_text,
            a.title,
            a.url,
            a.length_bytes,
            a.last_edited,
            VEC_DISTANCE_COSINE(
                ch.embedding,
                VEC_FromText(%s)
            ) AS distance
        FROM chunks AS ch
        JOIN articles AS a
            ON ch.article_id = a.article_id
        WHERE 1 = 1
    """

    # The first parameter is the query embedding.
    params = [embedding_text]

    # Restrict results to articles in a specific category.
    if category is not None:
        sql += """
            AND EXISTS (
                SELECT 1
                FROM article_categories AS ac
                JOIN categories AS c
                    ON ac.category_id = c.category_id
                WHERE ac.article_id = a.article_id
                  AND c.name = %s
            )
        """
        params.append(category)

    # Restrict results to articles edited after a specified date.
    if edited_after is not None:
        sql += """
            AND a.last_edited > %s
        """
        params.append(edited_after)

    # Restrict results by the article's content length in bytes.
    if min_length is not None:
        sql += """
            AND a.length_bytes >= %s
        """
        params.append(min_length)

    # Restrict results to articles linked from another article.
    if linked_from is not None:
        sql += """
            AND EXISTS (
                SELECT 1
                FROM article_links AS al
                WHERE al.source_article_id = %s
                  AND al.target_article_id = a.article_id
            )
        """
        params.append(linked_from)

    # Return the most similar chunks first.
    # Smaller cosine distance means greater semantic similarity.
    sql += """
        ORDER BY distance ASC
        LIMIT %s
    """

    params.append(limit)

    # Check whether this function needs its own connection.
    own_connection = connection is None

    # Create a connection only when one was not provided.
    if own_connection:
        connection = get_connection()

    try:
        # Execute the parameterized SQL query.
        with connection.cursor() as cursor:
            cursor.execute(sql, tuple(params))

            # Retrieve the matching chunks as dictionaries.
            results = cursor.fetchall()

        # Return the ranked search results.
        return results

    finally:
        # Close only connections created by this function.
        if own_connection:
            connection.close()