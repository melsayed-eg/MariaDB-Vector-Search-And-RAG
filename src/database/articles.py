from .connection import get_connection


def upsert_article(article, connection=None):
    # Check whether a connection was supplied by another function.
    own_connection = connection is None

    # Create a new connection if necessary.
    if own_connection:
        connection = get_connection()

    try:
        # Insert a new article, or update it if the ID already exists.
        sql = """
            INSERT INTO articles (
                article_id,
                title,
                url,
                content,
                length_bytes,
                last_edited
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                title = VALUES(title),
                url = VALUES(url),
                content = VALUES(content),
                length_bytes = VALUES(length_bytes),
                last_edited = VALUES(last_edited)
        """

        # Calculate the actual UTF-8 byte length of the article.
        length_bytes = len(article["content"].encode("utf-8"))

        # Prepare the values for the SQL placeholders.
        values = (
            article["article_id"],
            article["title"],
            article["url"],
            article["content"],
            length_bytes,
            article.get("last_edited")
        )

        # Execute the SQL query.
        with connection.cursor() as cursor:
            cursor.execute(sql, values)

        # Save changes if we created the connection.
        if own_connection:
            connection.commit()

    except Exception:
        # Undo changes if an error occurs.
        if own_connection:
            connection.rollback()
        raise

    finally:
        # Close only connections created by this function.
        if own_connection:
            connection.close()

def get_article(article_id, connection=None):
    # Check whether another function supplied a database connection.
    own_connection = connection is None

    # Open a connection if one wasn't provided.
    if own_connection:
        connection = get_connection()

    try:
        # Find the article with the specified Wikipedia page ID.
        sql = """
            SELECT
                article_id,
                title,
                url,
                content,
                length_bytes,
                last_edited,
                fetched_at
            FROM articles
            WHERE article_id = %s
        """

        # Create a cursor and execute the SQL query.
        with connection.cursor() as cursor:
            cursor.execute(sql, (article_id,))

            # Retrieve the first matching row.
            article = cursor.fetchone()

        # Return the article dictionary, or None if no row exists.
        return article

    finally:
        # Close the connection only if this function created it.
        if own_connection:
            connection.close()

def delete_article(article_id, connection=None):
    # Check whether another function supplied a connection.
    own_connection = connection is None

    # Open our own connection if necessary.
    if own_connection:
        connection = get_connection()

    try:
        # Delete the article matching the given Wikipedia page ID.
        sql = """
            DELETE FROM articles
            WHERE article_id = %s
        """

        with connection.cursor() as cursor:
            # Execute the DELETE statement safely.
            cursor.execute(sql, (article_id,))

            # Record how many articles were deleted.
            deleted_count = cursor.rowcount

        # Commit only if we created the connection.
        if own_connection:
            connection.commit()

        # Return the number of deleted articles.
        return deleted_count

    except Exception:
        # Undo changes if we own the transaction.
        if own_connection:
            connection.rollback()
        raise

    finally:
        # Close only connections we created.
        if own_connection:
            connection.close()