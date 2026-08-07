"""Carga y chunking del corpus de documentación.

Lee ``data/docs/*.md`` y trocea cada documento por sección (heading) en
``Chunk(doc_id, heading, text)``. El troceo por sección es deliberado: cada procedimiento
de los docs vive bajo su propio ``##``, así el retriever recupera la sección concreta que
responde la pregunta y no el documento entero, que mezclaría temas.

El ``text`` del chunk es lo que se indexa y lo que lee el LLM: lleva el título del documento
como prefijo (``"Devoluciones — Reembolso\n..."``) para que un fragmento sobre "reembolso"
conserve el contexto de que trata de devoluciones aunque se recupere aislado.

Cualquier fallo de lectura se propaga con contexto (qué fichero) en vez de degradar en
silencio a un corpus incompleto.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# El corpus vive en la raíz del repo (data/docs), no dentro del paquete. Se resuelve desde
# este fichero: .../src/ops_agent/rag/index.py -> parents[3] = raíz del repo.
DEFAULT_DOCS_DIR = Path(__file__).resolve().parents[3] / "data" / "docs"

# Encabezado markdown ATX: de uno a seis '#', un espacio y el texto del heading.
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


@dataclass(frozen=True)
class Chunk:
    """Una sección del corpus, unidad mínima de recuperación.

    ``text`` incluye el título del documento y el heading como prefijo; es lo que se embebe
    e indexa y lo que se le devuelve al LLM.
    """

    doc_id: str
    heading: str
    text: str


def _humanize(doc_id: str) -> str:
    """``entregas-fallidas`` -> ``Entregas fallidas`` para el título por defecto."""
    return doc_id.replace("-", " ").replace("_", " ").strip().capitalize()


def chunk_markdown(doc_id: str, markdown: str) -> list[Chunk]:
    """Trocea un documento markdown en un ``Chunk`` por sección.

    El primer ``#`` (H1) es el título del documento y da contexto a cada sección; los
    encabezados siguientes abren una sección nueva. El contenido anterior al primer
    encabezado de sección se descarta (en este corpus todo el contenido vive bajo un ``##``).
    """
    title = _humanize(doc_id)
    sections: list[tuple[str, list[str]]] = []
    heading: str | None = None
    body: list[str] = []

    for line in markdown.splitlines():
        match = _HEADING.match(line)
        if match is None:
            body.append(line)
            continue

        level = len(match.group(1))
        text = match.group(2).strip()
        # H1 al inicio del documento: es el título, no una sección.
        if level == 1 and heading is None and not any(prev.strip() for prev in body):
            title = text
            body = []
            continue
        if heading is not None:
            sections.append((heading, body))
        heading = text
        body = []

    if heading is not None:
        sections.append((heading, body))

    chunks: list[Chunk] = []
    for section_heading, section_body in sections:
        text_body = "\n".join(section_body).strip()
        composed = f"{title} — {section_heading}"
        if text_body:
            composed = f"{composed}\n{text_body}"
        chunks.append(Chunk(doc_id=doc_id, heading=section_heading, text=composed))
    return chunks


def load_corpus(docs_dir: Path = DEFAULT_DOCS_DIR) -> list[Chunk]:
    """Carga y trocea todos los ``.md`` de ``docs_dir`` en un índice de chunks en memoria.

    El orden de los ficheros es estable (alfabético) para que el índice sea reproducible.
    Falla con contexto si el directorio no existe o si el corpus queda vacío: un corpus vacío
    haría que el agente abstuviese de todo sin que nadie se enterase del porqué.
    """
    if not docs_dir.is_dir():
        raise RuntimeError(f"No existe el directorio del corpus RAG: {docs_dir}")

    chunks: list[Chunk] = []
    for path in sorted(docs_dir.glob("*.md")):
        try:
            markdown = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise RuntimeError(f"No se pudo leer el documento del corpus {path}") from exc
        chunks.extend(chunk_markdown(path.stem, markdown))

    if not chunks:
        raise RuntimeError(f"El corpus RAG en {docs_dir} está vacío o sin secciones ('## ...').")
    return chunks


__all__ = ["DEFAULT_DOCS_DIR", "Chunk", "chunk_markdown", "load_corpus"]
