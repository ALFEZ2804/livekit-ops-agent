"""Unit: corpus chunking and RAG retrievers.

Covers criterion 5 at the retrieval level: a covered question retrieves the right document;
an out-of-corpus question retrieves nothing (``select_relevant`` empty => the agent says it
doesn't know).

The deterministic case runs over ``Bm25Retriever`` (lexical, no network): the one CI can
always run. The ``EmbeddingRetriever`` (ONNX model, downloaded on first use) is also tested,
but the case is skipped if the model isn't available offline, so CI isn't forced onto the
network. Embedding assertions use top-k containment (tolerant to model nuance); BM25 ones use
top-1 because the lexical path is deterministic.
"""

from __future__ import annotations

import pytest

from ops_agent.rag.index import chunk_markdown, load_corpus
from ops_agent.rag.retriever import (
    Bm25Retriever,
    EmbeddingRetriever,
    Retriever,
    select_relevant,
)

CORPUS = load_corpus()

# Covered questions with lexical terms present in the target doc (for BM25, no stemming):
# (query, expected doc_id as top-1).
IN_CORPUS_LEXICAL = [
    ("retry attempts and notify the recipient", "entregas-fallidas"),
    ("how to reschedule the delivery and change the time window", "reprogramar-entrega"),
    ("return window and refund of the order", "devoluciones"),
    ("cut-off time and transit times for the express service", "plazos-y-ventanas"),
]

# Covered questions in natural / paraphrased language (for embeddings, which understand
# synonyms): the expected doc must be among the top-k.
IN_CORPUS_PARAPHRASE = [
    ("what happens if the driver finds nobody home?", "entregas-fallidas"),
    ("i need to move my parcel's appointment to another day", "reprogramar-entrega"),
    ("how long until i get my money back for a purchase?", "devoluciones"),
    ("when will it arrive if i send it express?", "plazos-y-ventanas"),
]

# Outside Nordport's domain: the retriever must not retrieve anything relevant.
OUT_OF_CORPUS = [
    "what is the capital of France?",
    "give me a recipe for a potato omelette",
    "who won the 2010 football world cup?",
]


@pytest.fixture(scope="module")
def bm25() -> Bm25Retriever:
    return Bm25Retriever(CORPUS)


@pytest.fixture(scope="module")
def embedding() -> EmbeddingRetriever:
    # The model downloads on first use; offline (CI) it isn't there and the case is skipped.
    # A code bug in the happy path shows up when run with the model cached.
    try:
        return EmbeddingRetriever(CORPUS)
    except Exception as exc:
        pytest.skip(f"EmbeddingRetriever not available offline (model/network): {exc}")


# --- Chunking -------------------------------------------------------------------------


def test_load_corpus_covers_all_documents() -> None:
    doc_ids = {chunk.doc_id for chunk in CORPUS}
    assert doc_ids == {
        "entregas-fallidas",
        "reprogramar-entrega",
        "plazos-y-ventanas",
        "devoluciones",
    }
    # Every chunk has indexable text and a heading; none empty.
    assert all(chunk.text.strip() and chunk.heading.strip() for chunk in CORPUS)


def test_chunk_markdown_splits_by_section() -> None:
    markdown = "# Title\n\n## One\nbody one\n\n## Two\nbody two\n"
    chunks = chunk_markdown("doc-demo", markdown)

    assert [c.heading for c in chunks] == ["One", "Two"]
    # The document title (H1) is propagated as context at the start of each chunk.
    assert chunks[0].text.startswith("Title — One")
    assert "body one" in chunks[0].text
    assert all(c.doc_id == "doc-demo" for c in chunks)


# --- BM25: deterministic, no network --------------------------------------------------


@pytest.mark.parametrize(("query", "expected_doc"), IN_CORPUS_LEXICAL)
def test_bm25_retrieves_expected_document(
    bm25: Bm25Retriever, query: str, expected_doc: str
) -> None:
    results = bm25.search(query, k=3)
    assert results, "BM25 should retrieve something for a covered query"
    assert results[0].doc_id == expected_doc
    assert results[0].score > 0.0


@pytest.mark.parametrize(("query", "expected_doc"), IN_CORPUS_LEXICAL)
def test_bm25_select_relevant_keeps_hits(
    bm25: Bm25Retriever, query: str, expected_doc: str
) -> None:
    relevant = select_relevant(bm25, query, k=3)
    assert relevant, "a covered question should not abstain"
    assert expected_doc in {chunk.doc_id for chunk in relevant}


@pytest.mark.parametrize("query", OUT_OF_CORPUS)
def test_bm25_abstains_out_of_corpus(bm25: Bm25Retriever, query: str) -> None:
    # With no content-term overlap, BM25 scores 0 and select_relevant abstains.
    assert select_relevant(bm25, query, k=3) == []


# --- Embeddings: default retriever (skipped if the model isn't offline) ---------------


@pytest.mark.parametrize(("query", "expected_doc"), IN_CORPUS_PARAPHRASE)
def test_embedding_retrieves_expected_document(
    embedding: EmbeddingRetriever, query: str, expected_doc: str
) -> None:
    results = select_relevant(embedding, query, k=3)
    assert results, "a covered paraphrased question should not abstain"
    assert expected_doc in {chunk.doc_id for chunk in results}


@pytest.mark.parametrize("query", OUT_OF_CORPUS)
def test_embedding_abstains_out_of_corpus(embedding: EmbeddingRetriever, query: str) -> None:
    assert select_relevant(embedding, query, k=3) == []


# --- Shared contract ------------------------------------------------------------------


def test_retrievers_satisfy_protocol() -> None:
    retrievers: list[Retriever] = [Bm25Retriever(CORPUS)]
    for retriever in retrievers:
        assert isinstance(retriever.min_score, float)
