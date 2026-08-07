"""RAG local: indexado del corpus y retrievers tras un ``Protocol`` común.

Reexporta la API pública para que los consumidores importen desde ``ops_agent.rag`` sin
conocer el reparto en ``index`` / ``retriever``. Importar el paquete NO carga fastembed:
el import de la librería de embeddings es perezoso, dentro de ``EmbeddingRetriever``.
"""

from .index import DEFAULT_DOCS_DIR, Chunk, chunk_markdown, load_corpus
from .retriever import (
    Bm25Retriever,
    EmbeddingRetriever,
    RetrievedChunk,
    Retriever,
    select_relevant,
)

__all__ = [
    "DEFAULT_DOCS_DIR",
    "Bm25Retriever",
    "Chunk",
    "EmbeddingRetriever",
    "RetrievedChunk",
    "Retriever",
    "chunk_markdown",
    "load_corpus",
    "select_relevant",
]
