"""Text cleaning and normalization for Wikipedia articles."""

from __future__ import annotations

import re
import unicodedata

from wikirag.errors import ValidationError


def clean_text(text: str) -> str:
    """Prepare and clean the plain text of a Wikipedia article.

    Maintains deterministic output, normalizing Unicode, stripping reference markers,
    and removing hidden formatting without stripping legitimate content.

    Args:
        text: Raw text string to clean.

    Returns:
        Fully cleaned and normalized string.

    Raises:
        ValidationError: If input is not a string.
    """
    if not isinstance(text, str):
        raise ValidationError("Input must be a string")

    # 1. Normalize line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # 2. Strip raw HTML tags & reference markers (e.g., [edit], [1], [citation needed])
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\[(?:edit|citation needed|\d+(?:,\s*\d+)*)\]", "", text, flags=re.IGNORECASE)

    # 3. Remove non-functional invisible characters (keep \u200c - ZWNJ)
    text = re.sub(r"[\u200b\u00ad\u2060\ufeff]", "", text)

    # 4. Unicode NFC normalization (must be done AFTER removing invisible characters)
    text = unicodedata.normalize("NFC", text)

    # 5. Collapse runs of horizontal spaces
    text = re.sub(r"[ \t\u00a0]+", " ", text)

    # 6. Clean start/end of lines
    lines = [line.strip() for line in text.split("\n")]

    # 7. Normalization of paragraph breaks & line runs
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()
