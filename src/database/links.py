from .connection import get_connection


def set_article_links(source_id, target_ids, connection=None):
    # Remove duplicate target IDs while preserving their order.
    target_ids = list(dict.fromkeys(target_ids))

    # Check whether the function needs to create its own connection.
    own_connection = connection is None

    # Create a new connection only if one was not provided.
    if own_connection:
        connection = get_connection()

    try:
        # Delete the existing outgoing links from this article.
        # This allows us to replace outdated links with new ones.
        sql = """
            DELETE FROM article_links
            WHERE source_article_id = %s
        """

        with connection.cursor() as cursor:
            # Remove the previous relationships.
            cursor.execute(sql, (source_id,))

            # SQL statement for inserting new article relationships.
            insert_sql = """
                INSERT INTO article_links (
                    source_article_id,
                    target_article_id
                )
                VALUES (%s, %s)
            """

            # Insert a relationship for each target article.
            for target_id in target_ids:
                cursor.execute(
                    insert_sql,
                    (source_id, target_id)
                )

        # Commit all changes together if this function owns the connection.
        if own_connection:
            connection.commit()

        # Return the number of outgoing links assigned to the article.
        return len(target_ids)

    except Exception:
        # Roll back all changes if an error occurs.
        # This prevents partial updates to the article's links.
        if own_connection:
            connection.rollback()
        raise

    finally:
        # Close only connections created by this function.
        if own_connection:
            connection.close()