"""Text cleaning and normalization for Wikipedia articles."""

from __future__ import annotations

import re
import unicodedata

from wikirag.errors import ValidationError

# Only match HTML tags (starts with a letter or /), preserving math inequalities like x < y and z > 0
_HTML_TAG_PATTERN = re.compile(r"</?[a-zA-Z][^>]*>")
_CITATION_PATTERN = re.compile(
    r"\[(?:edit|citation needed|\d+(?:,\s*\d+)*)\]", flags=re.IGNORECASE
)
_INVISIBLE_CHARS_PATTERN = re.compile(r"[\u200b\u00ad\u2060\ufeff]")
_HORIZONTAL_SPACE_PATTERN = re.compile(r"[ \t\u00a0]+")
_BLANK_LINES_PATTERN = re.compile(r"\n{3,}")


def clean_text(text: str) -> str:
    """Prepare and clean the plain text of a Wikipedia article.

    Maintains deterministic output, normalizing Unicode, stripping reference markers,
    and removing hidden formatting without stripping legitimate mathematical or text content.

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

    # 2. Strip HTML tags (preserving math inequalities like x < y and z > 0) & citation markers
    text = _HTML_TAG_PATTERN.sub("", text)
    text = _CITATION_PATTERN.sub("", text)

    # 3. Remove non-functional invisible characters (keep \u200c - ZWNJ)
    text = _INVISIBLE_CHARS_PATTERN.sub("", text)

    # 4. Unicode NFC normalization (must run AFTER invisible character removal)
    text = unicodedata.normalize("NFC", text)

    # 5. Collapse runs of horizontal spaces
    text = _HORIZONTAL_SPACE_PATTERN.sub(" ", text)

    # 6. Clean start/end of lines
    lines = [line.strip() for line in text.split("\n")]

    # 7. Normalization of paragraph breaks & line runs
    text = "\n".join(lines)
    text = _BLANK_LINES_PATTERN.sub("\n\n", text)

    return text.strip()