"""Extractive answer generation using retrieved WikiRAG context."""

from __future__ import annotations

import re
from typing import Protocol

from wikirag.errors import ValidationError
from wikirag.models import ContextBundle


class Generator(Protocol):
    """Define the interface expected by the RAG pipeline."""

    @property
    def name(self) -> str:
        """Return the generator's stable identifier."""
        ...

    def generate(self, question: str, context: ContextBundle) -> str:
        """Generate an answer grounded in the supplied context."""
        ...


class ExtractiveGenerator:
    """Build a deterministic answer by selecting sentences from context."""

    @property
    def name(self) -> str:
        """Return the generator's stable identifier."""
        return "extractive"

    def generate(self, question: str, context: ContextBundle) -> str:
        """Select relevant source sentences and preserve their citations.

        Args:
            question: Non-empty question to answer.
            context: Numbered source passages produced by ``build_context``.

        Returns:
            An extractive answer with numbered citations.

        Raises:
            ValidationError: If the question or context is invalid.
        """
        if not isinstance(question, str) or not question.strip():
            raise ValidationError("Question must be a non-empty string")

        if not isinstance(context, ContextBundle):
            raise ValidationError("context must be a ContextBundle")

        if not context.sources or not context.text.strip():
            raise ValidationError("Context must contain at least one source")

        question_terms = set(re.findall(r"\b[\w-]+\b", question.lower()))
        candidates: list[tuple[int, int, str]] = []

        for source_number, source in enumerate(context.sources, start=1):
            # Score sentences by question-term overlap, retaining source order.
            sentences = re.split(r"(?<=[.!?])\s+", source.text.strip())
            for sentence in sentences:
                sentence = sentence.strip()
                if not sentence:
                    continue

                sentence_terms = set(re.findall(r"\b[\w-]+\b", sentence.lower()))
                overlap = len(question_terms & sentence_terms)
                if overlap:
                    candidates.append((overlap, source_number, sentence))

        if not candidates:
            # Remain grounded even when lexical matching finds no overlap.
            source = context.sources[0]
            return f"{source.text.strip()} [1]"

        # Prefer greater overlap; ties retain the original passage order.
        candidates.sort(key=lambda item: -item[0])
        selected = candidates[:3]

        return " ".join(
            f"{sentence} [{source_number}]"
            for _, source_number, sentence in selected
        )
