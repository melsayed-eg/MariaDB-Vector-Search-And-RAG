"""Orchestrates Wikipedia snapshot ingestion into the database repository."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from wikirag.embeddings import Embedder
from wikirag.errors import ValidationError, WikiRagError
from wikirag.ingestion.chunking import split_into_chunks
from wikirag.ingestion.cleaning import clean_text
from wikirag.ingestion.wikipedia import load_snapshot
from wikirag.models import ArticleRecord, ChunkRecord, IngestOutcome, IngestReport


class IngestRepository(Protocol):
    """The repository methods needed by ingestion."""

    def ensure_embedding_meta(self, model_name: str, dim: int) -> None: ...

    def get_fingerprint(self, article_id: int) -> str | None: ...

    def ingest_article(
        self, article: ArticleRecord, chunks: Sequence[ChunkRecord]
    ) -> IngestOutcome: ...

    def resolve_links(self) -> int: ...


def _is_non_negative_int(value: object) -> bool:
    """Return whether a value is a real integer of at least zero."""
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def compute_fingerprint(
    cleaned_text: str,
    *,
    max_chars: int,
    overlap_chars: int,
    model_name: str,
) -> str:
    """Compute a deterministic SHA-256 fingerprint of an article and its settings.

    The same cleaned text, chunk settings and model always give the same value; changing
    any of them gives a different one.

    Args:
        cleaned_text: The cleaned article text.
        max_chars: Maximum characters per chunk.
        overlap_chars: Overlap between consecutive chunks.
        model_name: Name of the embedding model.

    Returns:
        A 64-character lowercase hexadecimal digest.

    Raises:
        ValidationError: If an argument has the wrong type or value.
    """
    if not isinstance(cleaned_text, str) or not cleaned_text:
        raise ValidationError("cleaned_text must be a non-empty string")
    if not isinstance(model_name, str) or not model_name.strip():
        raise ValidationError("model_name must be a non-empty string")
    if not _is_non_negative_int(max_chars) or max_chars < 1:
        raise ValidationError("max_chars must be a positive integer")
    if not _is_non_negative_int(overlap_chars):
        raise ValidationError("overlap_chars must be a non-negative integer")

    hasher = hashlib.sha256()
    # a NUL byte cannot appear in the parts, so different inputs never merge into one
    for part in (cleaned_text, str(max_chars), str(overlap_chars), model_name):
        hasher.update(part.encode())
        hasher.update(b"\0")
    return hasher.hexdigest()


def ingest_snapshot(
    snapshot_path: Path,
    repo: IngestRepository,
    embedder: Embedder,
    *,
    max_chars: int = 1000,
    overlap_chars: int = 150,
    limit: int | None = None,
) -> IngestReport:
    """Ingest the articles of a snapshot into the repository, skipping unchanged ones.

    The fingerprint is checked before any embedding work. A failure on one article is
    recorded in the report and the run continues. Links are resolved once at the end.

    Args:
        snapshot_path: Path to the JSONL snapshot file.
        repo: Repository that stores the articles.
        embedder: Embedder that creates the chunk vectors.
        max_chars: Maximum characters per chunk.
        overlap_chars: Overlap between consecutive chunks.
        limit: Process only the first ``limit`` articles; None means all.

    Returns:
        Counts of inserted, updated, skipped and failed articles.

    Raises:
        ValidationError: If an argument is invalid or the snapshot file is damaged.
        SchemaMismatchError: If the stored embedding model does not match the embedder.
    """
    if not _is_non_negative_int(max_chars) or max_chars < 1:
        raise ValidationError("max_chars must be a positive integer")
    if not _is_non_negative_int(overlap_chars) or overlap_chars >= max_chars:
        raise ValidationError("overlap_chars must be a non-negative integer below max_chars")
    if limit is not None and (not _is_non_negative_int(limit) or limit < 1):
        raise ValidationError("limit must be a positive integer or None")

    repo.ensure_embedding_meta(embedder.model_name, embedder.dim)

    inserted = 0
    updated = 0
    skipped = 0
    failed: list[tuple[str, str]] = []

    for position, raw in enumerate(load_snapshot(snapshot_path)):
        if limit is not None and position >= limit:
            break
        try:
            cleaned = clean_text(raw.text)
            if not cleaned:
                failed.append((raw.title, "Article text is empty after cleaning"))
                continue

            fingerprint = compute_fingerprint(
                cleaned,
                max_chars=max_chars,
                overlap_chars=overlap_chars,
                model_name=embedder.model_name,
            )

            # unchanged articles are skipped before any embedding work is done
            if repo.get_fingerprint(raw.article_id) == fingerprint:
                skipped += 1
                continue

            drafts = split_into_chunks(cleaned, max_chars=max_chars, overlap_chars=overlap_chars)
            vectors = embedder.embed_texts([draft.text for draft in drafts])
            if len(vectors) != len(drafts):
                raise WikiRagError("Embedder returned a different number of vectors than chunks")

            chunks = [
                ChunkRecord(
                    chunk_index=draft.chunk_index,
                    text=draft.text,
                    embedding=tuple(vector),
                    section_title=draft.section_title,
                )
                for draft, vector in zip(drafts, vectors, strict=True)
            ]
            article = ArticleRecord(
                article_id=raw.article_id,
                title=raw.title,
                url=raw.url,
                revision_id=raw.revision_id,
                fingerprint=fingerprint,
                revised_at=raw.revised_at,
                length_chars=len(cleaned),
                fetched_at=raw.fetched_at,
                topic=raw.topic,
                categories=raw.categories,
                linked_titles=raw.linked_titles,
            )

            outcome = repo.ingest_article(article, chunks)
            if outcome == "inserted":
                inserted += 1
            elif outcome == "updated":
                updated += 1
            else:
                skipped += 1
        except WikiRagError as error:
            # the repository rolls back its own transaction, so only this article is lost
            failed.append((raw.title, str(error)))

    repo.resolve_links()
    return IngestReport(
        inserted=inserted,
        updated=updated,
        skipped=skipped,
        failed=tuple(failed),
    )
