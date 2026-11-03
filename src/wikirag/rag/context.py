"""Build bounded, citation-ready context from retrieved Wikipedia chunks."""

from __future__ import annotations

from collections.abc import Sequence

from wikirag.errors import ValidationError
from wikirag.models import ContextBundle, SearchHit


def build_context(
    hits: Sequence[SearchHit],
    *,
    max_chars: int = 6000,
) -> ContextBundle:
    """Format ranked search hits into a bounded context with numbered citations.

    Hits retain their retrieval order. Duplicate chunk IDs are included only
    once, and chunks are never cut off partway through their text.

    Args:
        hits: Search results ordered by relevance.
        max_chars: Maximum length of the formatted context.

    Returns:
        A context bundle containing formatted text, included sources, and
        whether any unique source could not fit within the character limit.

    Raises:
        ValidationError: If ``max_chars`` is not a positive integer.
    """
    if not isinstance(max_chars, int) or isinstance(max_chars, bool) or max_chars < 1:
        raise ValidationError("max_chars must be a positive integer")

    seen_chunk_ids: set[int] = set()
    unique_hits: list[SearchHit] = []

    for hit in hits:
        if hit.chunk_id not in seen_chunk_ids:
            seen_chunk_ids.add(hit.chunk_id)
            unique_hits.append(hit)

    sections: list[str] = []
    included_hits: list[SearchHit] = []
    truncated = False

    for hit in unique_hits:
        citation_number = len(included_hits) + 1
        heading = f"[{citation_number}] {hit.article_title} — {hit.article_url}"
        if hit.section_title:
            heading += f"\nSection: {hit.section_title}"
        section = f"{heading}\n{hit.text}"
        candidate = "\n\n".join([*sections, section])

        if len(candidate) > max_chars:
            truncated = True
            break

        sections.append(section)
        included_hits.append(hit)

    return ContextBundle(
        text="\n\n".join(sections),
        sources=tuple(included_hits),
        truncated=truncated,
    )
