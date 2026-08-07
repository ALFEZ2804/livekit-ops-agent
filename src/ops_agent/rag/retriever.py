"""Retrievers del RAG local tras un Protocol común.

Responsabilidad (fase de implementación):
    - `RetrievedChunk(doc_id, text, score)`.
    - `Retriever` (Protocol) con `.search(query, k=3) -> list[RetrievedChunk]`
      (scores crudos; el umbral lo aplica el llamador).
    - `EmbeddingRetriever`: fastembed multilingüe + matriz numpy + coseno
      (default en runtime).
    - `Bm25Retriever`: determinista, sin red (CI / offline / fallback).

Por debajo del umbral => lista vacía => el LLM responde "no lo sé".

Andamiaje: sin implementar todavía.
"""
