"""Orchestrates Wikipedia snapshot ingestion into the database repository."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from pathlib import Path

from wikirag.db.repository import WikiRepository
from wikirag.embeddings import Embedder
from wikirag.errors import WikiRagError
from wikirag.ingestion.chunking import split_into_chunks
from wikirag.ingestion.cleaning import clean_text
from wikirag.ingestion.wikipedia import load_snapshot
from wikirag.models import ArticleRecord, ChunkRecord, IngestReport


def compute_fingerprint(
    cleaned_text: str,
    *,
    max_chars: int,
    overlap_chars: int,
    model_name: str,
) -> str:
    """Compute a deterministic 64-char SHA-256 fingerprint for article contents & settings."""
    hasher = hashlib.sha256()
    hasher.update(cleaned_text.encode("utf-8"))
    hasher.update(f"|max_chars={max_chars}|overlap_chars={overlap_chars}|model={model_name}".encode("utf-8"))
    return hasher.hexdigest()


def ingest_snapshot(
    snapshot_path: Path,
    repo: WikiRepository,
    embedder: Embedder,
    *,
    max_chars: int = 1000,
    overlap_chars: int = 150,
    limit: int | None = None,
) -> IngestReport:
    """Ingest articles and chunks from a snapshot into the repository idempotently.

    Args:
        snapshot_path: Path to the JSONL snapshot file.
        repo: Database repository implementing WikiRepository.
        embedder: Embedder model generating vectors.
        max_chars: Maximum characters per text chunk.
        overlap_chars: Overlapping characters between consecutive chunks.
        limit: Optional limit on the number of articles to process.

    Returns:
        An IngestReport with counts of inserted, updated, skipped, and failed articles.
    """
    repo.ensure_embedding_meta(embedder.model_name, embedder.dim)

    inserted = 0
    updated = 0
    skipped = 0
    failed: list[tuple[str, str]] = []

    articles = list(load_snapshot(snapshot_path))
    if limit is not None and limit > 0:
        articles = articles[:limit]

    for raw in articles:
        try:
            cleaned = clean_text(raw.text)
            if not cleaned:
                failed.append((raw.title, "Article text is empty after cleaning"))
                continue

            current_fingerprint = compute_fingerprint(
                cleaned,
                max_chars=max_chars,
                overlap_chars=overlap_chars,
                model_name=embedder.model_name,
            )

            stored_fingerprint = repo.get_fingerprint(raw.article_id)
            if stored_fingerprint == current_fingerprint:
                skipped += 1
                continue

            # Split into chunks
            chunk_drafts = split_into_chunks(
                cleaned,
                max_chars=max_chars,
                overlap_chars=overlap_chars,
            )

            chunk_texts = [c.text for c in chunk_drafts]
            embeddings = embedder.embed_texts(chunk_texts)

            chunk_records: list[ChunkRecord] = [
                ChunkRecord(
                    chunk_index=draft.chunk_index,
                    text=draft.text,
                    embedding=tuple(embeddings[idx]),
                    section_title=draft.section_title,
                )
                for idx, draft in enumerate(chunk_drafts)
            ]

            article_record = ArticleRecord(
                article_id=raw.article_id,
                title=raw.title,
                url=raw.url,
                revision_id=raw.revision_id,
                fingerprint=current_fingerprint,
                revised_at=raw.revised_at,
                length_chars=len(cleaned),
                fetched_at=raw.fetched_at,
                topic=raw.topic,
                categories=tuple(raw.categories),
                linked_titles=tuple(raw.linked_titles),
            )

            outcome = repo.ingest_article(article_record, chunk_records)
            if outcome == "inserted":
                inserted += 1
            elif outcome == "updated":
                updated += 1
            else:
                skipped += 1

        except (WikiRagError, Exception) as err:
            failed.append((raw.title, str(err)))

    repo.resolve_links()

    return IngestReport(
        inserted=inserted,
        updated=updated,
        skipped=skipped,
        failed=tuple(failed),
    )