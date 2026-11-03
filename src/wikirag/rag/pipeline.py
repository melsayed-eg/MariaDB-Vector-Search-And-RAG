"""Orchestrate retrieval, context building, and answer generation."""

from __future__ import annotations

import re
from time import perf_counter

from wikirag.errors import WikiRagError
from wikirag.models import RAGAnswer, SearchFilters
from wikirag.rag.context import build_context
from wikirag.rag.generator import Generator
from wikirag.retrieval.retriever import Retriever

_NO_INFORMATION = (
    "I don't have enough information in the retrieved sources to answer this question."
)


def answer_question(
    question: str,
    retriever: Retriever,
    generator: Generator,
    *,
    top_k: int = 5,
    mode: str = "semantic",
    filters: SearchFilters | None = None,
    max_context_chars: int = 6000,
) -> RAGAnswer:
    """Retrieve relevant passages and generate a grounded answer.

    Args:
        question: The user's question.
        retriever: Component used to retrieve relevant chunks.
        generator: Component used to generate an answer from context.
        top_k: Maximum number of chunks to retrieve.
        mode: Retrieval mode.
        filters: Optional filters for hybrid retrieval.
        max_context_chars: Maximum formatted context length.

    Returns:
        An answer with its context, retrieval results, and timing.

    Raises:
        WikiRagError: If generation fails or returns invalid citations.
    """
    started = perf_counter()

    retrieval = retriever.retrieve(
        question,
        top_k=top_k,
        mode=mode,
        filters=filters,
    )
    context = build_context(retrieval.hits, max_chars=max_context_chars)

    if not context.sources:
        answer = _NO_INFORMATION
    else:
        try:
            answer = generator.generate(question, context)
        except WikiRagError:
            raise
        except Exception as exc:
            raise WikiRagError("Answer generation failed") from exc

        if not isinstance(answer, str) or not answer.strip():
            raise WikiRagError("Generator returned an empty or invalid answer")

        citations = [int(number) for number in re.findall(r"\[(\d+)\]", answer)]
        if not citations or any(
            number < 1 or number > len(context.sources) for number in citations
        ):
            raise WikiRagError("Generated answer must cite at least one available source")

    return RAGAnswer(
        question=question,
        answer=answer,
        context=context,
        retrieval=retrieval,
        generator_name=generator.name,
        latency_ms=(perf_counter() - started) * 1000,
    )
