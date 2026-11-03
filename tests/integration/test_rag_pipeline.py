"""End-to-end RAG integration against isolated MariaDB."""

from contextlib import closing
from dataclasses import replace
from datetime import datetime

import pytest
from fakes import FakeEmbedder

from wikirag.config import EMBEDDING_DIM, load_settings
from wikirag.db.connection import get_connection
from wikirag.db.repository import WikiRepository
from wikirag.db.schema import init_schema
from wikirag.errors import ValidationError
from wikirag.rag.generator import ExtractiveGenerator
from wikirag.rag.pipeline import answer_question
from wikirag.retrieval.retriever import Retriever


@pytest.fixture
def test_db_config():
    settings = load_settings()
    if not settings.db_name_test.endswith("_test") or settings.db_name_test == settings.db.database:
        raise ValidationError("A separate test database is required")

    config = replace(settings.db, database=settings.db_name_test)
    with closing(get_connection(config)) as conn:
        init_schema(conn, recreate=True)
    return config


def test_rag_pipeline_with_mariadb(test_db_config):
    from wikirag.models import ArticleRecord, ChunkRecord

    vector = (1.0,) + (0.0,) * (EMBEDDING_DIM - 1)
    article = ArticleRecord(
        article_id=999001,
        title="Physics",
        url="https://en.wikipedia.org/wiki/Physics",
        revision_id=1,
        fingerprint="a" * 64,
        revised_at=datetime(2026, 1, 1),
        length_chars=len("Physics explains motion."),
        fetched_at=datetime(2026, 1, 2),
    )
    chunk = ChunkRecord(
        chunk_index=0,
        text="Physics explains motion.",
        embedding=vector,
    )

    with WikiRepository(test_db_config) as repo:
        repo.ingest_article(article, [chunk])
        retriever = Retriever(repo, FakeEmbedder())
        result = answer_question(
            "What does physics explain?",
            retriever,
            ExtractiveGenerator(),
            top_k=1,
        )

    assert "motion" in result.answer.lower()
    assert "[1]" in result.answer
