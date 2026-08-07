"""Retrievers del RAG local tras un ``Protocol`` común.

Dos implementaciones intercambiables:

- ``EmbeddingRetriever``: embeddings multilingües locales (fastembed, ONNX CPU) + coseno
  sobre una matriz numpy. Es el retriever por defecto en runtime: entiende paráfrasis y
  sinónimos, así que recupera aunque la pregunta no use las palabras exactas del doc.
- ``Bm25Retriever``: recuperación léxica determinista sin red (rank-bm25). Se usa en CI,
  offline y como fallback documentado. Mismo contrato, resultado reproducible.

``search`` devuelve los ``k`` mejores chunks con su **score crudo**; el umbral lo aplica el
llamador vía :func:`select_relevant`. La abstención (criterio 5) es que ``select_relevant``
devuelva lista vacía cuando nada supera el ``min_score`` del retriever, y entonces el LLM
responde que no lo sabe.

Por qué cada retriever lleva su propio ``min_score``: los scores de coseno (acotados, ~0 a 1)
y los de BM25 (léxicos, sin cota superior, exactamente 0 sin solape de términos) viven en
escalas distintas; un único umbral global no sirve para ambos. Cada impl fija el suelo
adecuado a su métrica y el llamador solo pregunta "¿supera tu umbral?".
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np
from numpy.typing import NDArray
from rank_bm25 import BM25Okapi

from .index import Chunk

# Modelo multilingüe verificado contra TextEmbedding.list_supported_models() (fastembed
# 0.8): paráfrasis multilingüe, ONNX CPU, sin torch. Descarga una vez a la caché de
# fastembed en la primera construcción; después corre offline.
DEFAULT_EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

# Suelo de coseno para abstención del retriever de embeddings. Calibrado sobre el corpus en
# inglés (paraphrase-multilingual-MiniLM, mean pooling): las preguntas cubiertas puntúan por
# encima de ~0.29 y las de fuera de dominio por debajo de ~0.11. Se corta en 0.20, a mitad
# del hueco. Reajustar si cambia el corpus o el modelo.
DEFAULT_EMBEDDING_MIN_SCORE = 0.20

# BM25 da exactamente 0 cuando ningún término de la consulta aparece en el corpus, y un
# valor claramente positivo en cuanto hay solape. Este epsilon separa "no encontró nada"
# de "encontró algo" sin filtrar coincidencias reales.
DEFAULT_BM25_MIN_SCORE = 1e-6


@dataclass(frozen=True)
class RetrievedChunk:
    """Un chunk recuperado con su score crudo (sin umbral aplicado)."""

    doc_id: str
    text: str
    score: float


class Retriever(Protocol):
    """Contrato de recuperación. El resto del código depende de esto, no de la impl.

    ``min_score`` es el suelo por debajo del cual un resultado se considera irrelevante para
    esta métrica; lo lee :func:`select_relevant`.
    """

    min_score: float

    def search(self, query: str, k: int = 3) -> list[RetrievedChunk]:
        """Devuelve los ``k`` mejores chunks por score, con scores crudos y sin filtrar."""
        ...


def select_relevant(retriever: Retriever, query: str, k: int = 3) -> list[RetrievedChunk]:
    """Aplica el umbral del retriever: descarta lo que cae por debajo de ``min_score``.

    Fuente única de la abstención (criterio 5): lista vacía => el agente dice que no lo sabe.
    La usan tanto la tool ``search_docs`` como los tests, para que umbral y comportamiento no
    se dupliquen.
    """
    return [chunk for chunk in retriever.search(query, k) if chunk.score >= retriever.min_score]


def _l2_normalize(matrix: NDArray[np.float32]) -> NDArray[np.float32]:
    """Normaliza filas a norma 1 para que el producto punto sea coseno. Evita dividir por 0."""
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms = np.where(norms == 0.0, 1.0, norms)
    return (matrix / norms).astype(np.float32)


def _top_k(chunks: list[Chunk], scores: NDArray[np.float64], k: int) -> list[RetrievedChunk]:
    """Empaqueta los ``k`` mejores chunks por score. Orden estable en empates (por índice)."""
    if k <= 0:
        return []
    order = np.argsort(-scores, kind="stable")[:k]
    return [
        RetrievedChunk(doc_id=chunks[i].doc_id, text=chunks[i].text, score=float(scores[i]))
        for i in (int(j) for j in order)
    ]


class EmbeddingRetriever:
    """Retriever por defecto: embeddings multilingües locales + coseno sobre matriz numpy.

    Embebe todo el corpus una sola vez al construirse; cada ``search`` solo embebe la consulta
    y hace un producto matriz-vector, sin red (el modelo ONNX corre en CPU en local), así que
    no hay llamada de red por consulta que acotar con timeout.
    """

    def __init__(
        self,
        chunks: list[Chunk],
        *,
        model_name: str = DEFAULT_EMBEDDING_MODEL,
        min_score: float = DEFAULT_EMBEDDING_MIN_SCORE,
        cache_dir: str | None = None,
    ) -> None:
        if not chunks:
            raise RuntimeError("EmbeddingRetriever necesita un corpus no vacío.")
        # Import perezoso: mantener el camino BM25/offline (CI) libre de cargar fastembed y
        # onnxruntime, que solo hacen falta si de verdad se construye este retriever.
        from fastembed import TextEmbedding

        self._chunks = chunks
        self.min_score = min_score
        self._model: Any = TextEmbedding(model_name=model_name, cache_dir=cache_dir)
        vectors = np.asarray(list(self._model.embed([c.text for c in chunks])), dtype=np.float32)
        self._matrix: NDArray[np.float32] = _l2_normalize(vectors)

    def search(self, query: str, k: int = 3) -> list[RetrievedChunk]:
        raw = np.asarray(next(iter(self._model.embed([query]))), dtype=np.float32)
        query_vec = _l2_normalize(raw[np.newaxis, :])[0]
        scores = (self._matrix @ query_vec).astype(np.float64)
        return _top_k(self._chunks, scores, k)


# --- Tokenización léxica para BM25 -----------------------------------------------------

# Common English stopwords: removed so BM25 abstention depends on content words, not
# connectors. Without this, "the"/"of" in an out-of-domain question would score against the
# corpus (where they appear everywhere) and the retriever would fail to abstain.
_STOPWORDS_TEXT = (
    "a about above after again against all am an and any are aren as at be because been "
    "before being below between both but by can cannot could did do does doing don down "
    "during each few for from further had has have having he her here hers herself him "
    "himself his how i if in into is it its itself just me more most my myself no nor not "
    "of off on once only or other our ours ourselves out over own same she should so some "
    "such than that the their theirs them themselves then there these they this those "
    "through to too under until up very was we were what when where which while who whom "
    "why will with would you your yours yourself yourselves"
)
_STOPWORDS = frozenset(_STOPWORDS_TEXT.split())

_TOKEN = re.compile(r"[a-z0-9]+")


def _strip_accents(text: str) -> str:
    """Quita tildes/diacríticos (NFKD + descarte de marcas) para casar 'tránsito'~'transito'."""
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _tokenize(text: str) -> list[str]:
    """Minúsculas, sin tildes, palabras de >=2 letras y sin stopwords. Determinista, sin red."""
    normalized = _strip_accents(text.lower())
    return [tok for tok in _TOKEN.findall(normalized) if len(tok) > 1 and tok not in _STOPWORDS]


class Bm25Retriever:
    """Retriever léxico determinista (BM25 Okapi) sin red. Para CI, offline y fallback.

    Tokeniza corpus y consulta con el mismo normalizador (minúsculas, sin tildes, sin
    stopwords), de modo que la relevancia depende de las palabras de contenido.
    """

    def __init__(self, chunks: list[Chunk], *, min_score: float = DEFAULT_BM25_MIN_SCORE) -> None:
        if not chunks:
            raise RuntimeError("Bm25Retriever necesita un corpus no vacío.")
        self._chunks = chunks
        self.min_score = min_score
        self._bm25 = BM25Okapi([_tokenize(c.text) for c in chunks])

    def search(self, query: str, k: int = 3) -> list[RetrievedChunk]:
        tokens = _tokenize(query)
        # get_scores([]) devuelve todo ceros: una consulta sin palabras de contenido no casa
        # con nada y el llamador abstiene.
        scores = np.asarray(self._bm25.get_scores(tokens), dtype=np.float64)
        return _top_k(self._chunks, scores, k)


__all__ = [
    "DEFAULT_BM25_MIN_SCORE",
    "DEFAULT_EMBEDDING_MIN_SCORE",
    "DEFAULT_EMBEDDING_MODEL",
    "Bm25Retriever",
    "EmbeddingRetriever",
    "RetrievedChunk",
    "Retriever",
    "select_relevant",
]
