from .connection import get_connection
from .articles import upsert_article
from .chunks import replace_article_chunks
from .categories import set_article_categories
from .links import set_article_links


def save_article_with_metadata(
    article,
    chunks,
    categories,
    links,
    connection=None
):
    """
    Save an article and its related data in one transaction.

    article: Dictionary containing Wikipedia article metadata.
    chunks: List of dictionaries containing text and embeddings.
    categories: List of category names.
    links: List of target Wikipedia article IDs.

    Returns the saved article ID.
    """

    # Use an existing connection if provided.
    own_connection = connection is None

    if own_connection:
        connection = get_connection()

    try:
        # Save the article itself.
        upsert_article(article, connection=connection)

        # Replace its existing chunks and embeddings.
        replace_article_chunks(
            article["article_id"],
            chunks,
            connection=connection
        )

        # Replace its category relationships.
        set_article_categories(
            article["article_id"],
            categories,
            connection=connection
        )

        # Replace its outgoing article links.
        set_article_links(
            article["article_id"],
            links,
            connection=connection
        )

        # Commit only if this function owns the connection.
        if own_connection:
            connection.commit()

        return article["article_id"]

    except Exception:
        # Roll back every operation if anything fails.
        if own_connection:
            connection.rollback()

        raise

    finally:
        # Do not close a connection supplied by the caller.
        if own_connection:
            connection.close()