-- Table 1: Store Wikipedia articles and their metadata.

CREATE TABLE IF NOT EXISTS articles (
    article_id BIGINT PRIMARY KEY,
    title VARCHAR(512) NOT NULL,
    url TEXT NOT NULL,
    content LONGTEXT NOT NULL,
    length_bytes INT UNSIGNED,
    last_edited DATETIME,
    fetched_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 2: Store article chunks and their vector embeddings.

CREATE TABLE IF NOT EXISTS chunks (
    chunk_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    article_id BIGINT NOT NULL,
    chunk_index INT UNSIGNED NOT NULL,
    chunk_text TEXT NOT NULL,
    embedding VECTOR(384) NOT NULL,

    CONSTRAINT fk_chunks_article
        FOREIGN KEY (article_id)
        REFERENCES articles(article_id)
        ON DELETE CASCADE,

    CONSTRAINT uq_article_chunk
        UNIQUE (article_id, chunk_index),

    VECTOR INDEX (embedding) M=8 DISTANCE=cosine
) ENGINE=InnoDB;

-- Table 3: Store unique Wikipedia categories.

CREATE TABLE IF NOT EXISTS categories (
    category_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(512) NOT NULL UNIQUE
) ENGINE=InnoDB;

-- Table 4: Connect Wikipedia articles to their categories.

CREATE TABLE IF NOT EXISTS article_categories (
    article_id BIGINT NOT NULL,
    category_id BIGINT NOT NULL,

    PRIMARY KEY (article_id, category_id),

    CONSTRAINT fk_article_categories_article
        FOREIGN KEY (article_id)
        REFERENCES articles(article_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_article_categories_category
        FOREIGN KEY (category_id)
        REFERENCES categories(category_id)
        ON DELETE CASCADE
) ENGINE=InnoDB;

-- Table 5: Store links between Wikipedia articles.

CREATE TABLE IF NOT EXISTS article_links (
    source_article_id BIGINT NOT NULL,
    target_article_id BIGINT NOT NULL,

    PRIMARY KEY (source_article_id, target_article_id),

    CONSTRAINT fk_links_source
        FOREIGN KEY (source_article_id)
        REFERENCES articles(article_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_links_target
        FOREIGN KEY (target_article_id)
        REFERENCES articles(article_id)
        ON DELETE CASCADE
) ENGINE=InnoDB;