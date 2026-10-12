from .connection import get_connection


def set_article_categories(article_id, category_names, connection=None):
    # Check whether the function needs to create its own connection.
    own_connection = connection is None

    # Create a new connection only if one was not provided.
    if own_connection:
        connection = get_connection()

    try:
        # Remove duplicate category names while preserving their order.
        category_names = list(dict.fromkeys(category_names))

        with connection.cursor() as cursor:

            # Remove the article's existing category associations.
            # The categories themselves are NOT deleted.
            cursor.execute(
                "DELETE FROM article_categories WHERE article_id = %s",
                (article_id,)
            )

            # Process each category associated with the article.
            for name in category_names:

                # Insert the category if it does not already exist.
                # If it exists, reuse its existing category_id.
                cursor.execute(
                    """
                    INSERT INTO categories (name)
                    VALUES (%s)
                    ON DUPLICATE KEY UPDATE
                        category_id = LAST_INSERT_ID(category_id)
                    """,
                    (name,)
                )

                # Retrieve the ID of the newly created or existing category.
                category_id = cursor.lastrowid

                # Connect the article to this category.
                cursor.execute(
                    """
                    INSERT INTO article_categories (
                        article_id,
                        category_id
                    )
                    VALUES (%s, %s)
                    """,
                    (article_id, category_id)
                )

        # Commit all changes together if this function owns the connection.
        if own_connection:
            connection.commit()

    except Exception:
        # Undo all changes if an error occurs.
        if own_connection:
            connection.rollback()
        raise

    finally:
        # Close only connections created by this function.
        if own_connection:
            connection.close()