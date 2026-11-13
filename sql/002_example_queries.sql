
-- MariaDB WikiRAG: native vector search and relational SQL demonstrations.
-- Area 4 blueprint examples Q1-Q6, adapted to the CS Wikipedia corpus.
--
-- Prerequisites:
-- 1. MariaDB 11.8 and sql/001_schema.sql are initialized.
-- 2. The 200-article Wikipedia snapshot is ingested with vectors.
-- 3. In-corpus Wikipedia links have been resolved.
--
-- Q1-Q5 are read-only SQL demonstrations.
-- Parameters are derived from actual articles, categories, and links.
-- Application code must use bound SQL parameters for user inputs.

-- Find a source article with a topic and stored chunks, linking to
-- a destination that has chunks and at least one category.
SET @hub_article_id = (
    SELECT l.source_article_id
    FROM links AS l
    JOIN articles AS src
        ON src.article_id = l.source_article_id
    JOIN articles AS dst
        ON dst.article_id = l.target_article_id
    WHERE src.topic IS NOT NULL
      AND dst.length_chars > 0
      AND EXISTS (
          SELECT 1
          FROM chunks AS c
          WHERE c.article_id = src.article_id
      )
      AND EXISTS (
          SELECT 1
          FROM chunks AS c
          WHERE c.article_id = dst.article_id
      )
      AND EXISTS (
          SELECT 1
          FROM article_categories AS ac
          WHERE ac.article_id = dst.article_id
      )
    ORDER BY l.source_article_id, l.target_article_id
    LIMIT 1
);

-- Select a linked destination satisfying the same requirements.
SET @target_article_id = (
    SELECT l.target_article_id
    FROM links AS l
    JOIN articles AS dst
        ON dst.article_id = l.target_article_id
    WHERE l.source_article_id = @hub_article_id
      AND dst.length_chars > 0
      AND EXISTS (
          SELECT 1
          FROM chunks AS c
          WHERE c.article_id = dst.article_id
      )
      AND EXISTS (
          SELECT 1
          FROM article_categories AS ac
          WHERE ac.article_id = dst.article_id
      )
    ORDER BY l.target_article_id
    LIMIT 1
);

-- Choose a valid Computer Science topic from the source article.
SET @topic = (
    SELECT a.topic
    FROM articles AS a
    WHERE a.article_id = @hub_article_id
);

-- Choose a real Wikipedia category from the destination article.
SET @category = (
    SELECT cat.name
    FROM article_categories AS ac
    JOIN categories AS cat
        ON cat.category_id = ac.category_id
    WHERE ac.article_id = @target_article_id
    ORDER BY cat.name
    LIMIT 1
);

-- Select thresholds that match the chosen destination.
-- These demonstrate combined predicates, not filter selectivity.
SET @min_length_chars = (
    SELECT a.length_chars - 1
    FROM articles AS a
    WHERE a.article_id = @target_article_id
);

SET @edited_since = (
    SELECT a.revised_at
    FROM articles AS a
    WHERE a.article_id = @target_article_id
);

-- Use real stored vectors as reproducible example query vectors.
SET @q = (
    SELECT VEC_ToText(c.embedding)
    FROM chunks AS c
    WHERE c.article_id = @hub_article_id
    ORDER BY c.chunk_index
    LIMIT 1
);

SET @q_target = (
    SELECT VEC_ToText(c.embedding)
    FROM chunks AS c
    WHERE c.article_id = @target_article_id
    ORDER BY c.chunk_index
    LIMIT 1
);

-- Show the parameters selected from the actual Wikipedia corpus.
-- Both IDs and the category should be non-NULL after full ingestion.
SELECT
    @hub_article_id AS source_article_id,
    @target_article_id AS linked_target_article_id,
    @topic AS source_topic,
    @category AS target_category,
    @min_length_chars AS minimum_length_chars,
    @edited_since AS edited_since;

-- Q1: Pure semantic top-5 using MariaDB's native vector index.
-- Rank vectors before joining relational metadata.
SELECT
    ranked.chunk_id,
    ranked.article_id,
    a.title,
    a.url,
    ranked.distance
FROM (
    SELECT
        c.chunk_id,
        c.article_id,
        VEC_DISTANCE_COSINE(
            c.embedding,
            VEC_FromText(@q)
        ) AS distance
    FROM chunks AS c
    ORDER BY VEC_DISTANCE_COSINE(
        c.embedding,
        VEC_FromText(@q)
    ) ASC
    LIMIT 5
) AS ranked
JOIN articles AS a
    ON a.article_id = ranked.article_id
ORDER BY
    ranked.distance,
    ranked.article_id,
    ranked.chunk_id;

-- Q2: Semantic search constrained by a relational topic.
-- Exact ranking applies the topic filter before LIMIT.
SELECT
    c.chunk_id,
    a.title,
    a.topic,
    VEC_DISTANCE_COSINE(
        c.embedding,
        VEC_FromText(@q)
    ) AS distance
FROM chunks AS c IGNORE INDEX (embedding)
JOIN articles AS a
    ON a.article_id = c.article_id
WHERE LOWER(a.topic) = LOWER(@topic)
ORDER BY
    distance,
    a.article_id,
    c.chunk_index,
    c.chunk_id
LIMIT 5;

-- Q3: Semantic search constrained by a Wikipedia category.
-- The many-to-many relationship is queried inside MariaDB.
SELECT
    c.chunk_id,
    a.title,
    cat.name AS matched_category,
    VEC_DISTANCE_COSINE(
        c.embedding,
        VEC_FromText(@q_target)
    ) AS distance
FROM chunks AS c IGNORE INDEX (embedding)
JOIN articles AS a
    ON a.article_id = c.article_id
JOIN article_categories AS ac
    ON ac.article_id = a.article_id
JOIN categories AS cat
    ON cat.category_id = ac.category_id
WHERE LOWER(cat.name) = LOWER(@category)
ORDER BY
    distance,
    a.article_id,
    c.chunk_index,
    c.chunk_id
LIMIT 5;

-- Q4: Expand semantically ranked passages through Wikipedia links.
-- Restrict the candidate passages to sources with resolved links.
-- Exact ranking ensures link eligibility before the top-5 limit.
WITH top_linked_chunks AS (
    SELECT
        c.chunk_id,
        c.article_id
    FROM chunks AS c IGNORE INDEX (embedding)
    WHERE EXISTS (
        SELECT 1
        FROM links AS l
        WHERE l.source_article_id = c.article_id
          AND l.target_article_id IS NOT NULL
    )
    ORDER BY
        VEC_DISTANCE_COSINE(
            c.embedding,
            VEC_FromText(@q)
        ),
        c.article_id,
        c.chunk_index,
        c.chunk_id
    LIMIT 5
)
SELECT DISTINCT
    src.article_id AS source_article_id,
    src.title AS found_in,
    dst.article_id AS linked_article_id,
    dst.title AS linked_article
FROM top_linked_chunks AS t
JOIN articles AS src
    ON src.article_id = t.article_id
JOIN links AS l
    ON l.source_article_id = t.article_id
JOIN articles AS dst
    ON dst.article_id = l.target_article_id
ORDER BY
    source_article_id,
    linked_article_id
LIMIT 15;

-- Q5: Hybrid SQL retrieval combining several relational constraints.
-- Category, article length, revision date, and a resolved incoming
-- link are applied before exact cosine ranking and top-K selection.
SELECT
    c.chunk_id,
    a.article_id,
    a.title,
    a.length_chars,
    a.revised_at,
    VEC_DISTANCE_COSINE(
        c.embedding,
        VEC_FromText(@q_target)
    ) AS distance
FROM chunks AS c IGNORE INDEX (embedding)
JOIN articles AS a
    ON a.article_id = c.article_id
WHERE a.length_chars > @min_length_chars
  AND a.revised_at >= CAST(@edited_since AS DATETIME)
  AND EXISTS (
      SELECT 1
      FROM article_categories AS ac
      JOIN categories AS cat
          ON cat.category_id = ac.category_id
      WHERE ac.article_id = a.article_id
        AND LOWER(cat.name) = LOWER(@category)
  )
  AND EXISTS (
      SELECT 1
      FROM links AS l
      WHERE l.source_article_id = @hub_article_id
        AND l.target_article_id = a.article_id
  )
ORDER BY
    distance,
    a.article_id,
    c.chunk_index,
    c.chunk_id
LIMIT 5;

-- Q6: Two-session transaction-visibility demonstration.
-- This example is deliberately commented out and is NOT executed.
-- Perform this only against the isolated test database.
--
-- SESSION A:
--
-- SET @demo_article_id = (
--     SELECT article_id
--     FROM chunks
--     ORDER BY chunk_id
--     LIMIT 1
-- );
--
-- SET @demo_vector = (
--     SELECT VEC_ToText(embedding)
--     FROM chunks
--     ORDER BY chunk_id
--     LIMIT 1
-- );
--
-- SET @demo_chunk_index = (
--     SELECT COALESCE(MAX(chunk_index), -1) + 1
--     FROM chunks
--     WHERE article_id = @demo_article_id
-- );
--
-- START TRANSACTION;
--
-- INSERT INTO chunks (
--     article_id,
--     chunk_index,
--     section_title,
--     text,
--     char_count,
--     embedding
-- )
-- VALUES (
--     @demo_article_id,
--     @demo_chunk_index,
--     NULL,
--     'WikiRAG uncommitted visibility demo',
--     CHAR_LENGTH('WikiRAG uncommitted visibility demo'),
--     VEC_FromText(@demo_vector)
-- );
--
-- Keep transaction A open without committing.
--
-- SESSION B:
--
-- SELECT COUNT(*) AS visible_chunks
-- FROM chunks
-- WHERE text = 'WikiRAG uncommitted visibility demo';
--
-- Expected: 0, because session A has not committed.
--
-- SESSION A:
--
-- ROLLBACK;
--
-- SESSION B:
--
-- Run the same SELECT again.
-- Expected: 0, because the insert was rolled back.
--
-- To test visibility after COMMIT under different isolation levels,
-- use the project's isolated transaction-visibility experiment.
