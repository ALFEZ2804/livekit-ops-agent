"""Fixtures compartidas de la suite de evals (framework de LiveKit Agents).

Las evals ejercitan el **agente real** (`OpsAgent`, con sus tres tools y su prompt) contra
el LLM real de Anthropic, en **modo texto y sin audio**: `AgentSession` se construye solo
con `llm=` (ni STT, ni TTS, ni VAD), se arranca sin `room`, y se conduce con
`session.run(user_input=...)`. Así corre headless, sin micrófono ni credenciales de LiveKit
Cloud (SPEC §4).

Determinismo donde importa:
- `AgentDeps` usa el `JsonShipmentRepository` fijo (incluye el pedido 1024) y el `Bm25Retriever`
  léxico, que no necesita red ni descarga de modelos: el RAG de las evals es reproducible.
- El LLM sí es real (elige tools y redacta), así que las evals dependen de red + clave de
  Anthropic. Si la clave no está, la suite de evals se **salta** (no falla), igual que las
  pruebas de embeddings offline.

El mismo `llm` juzga (`expect().judge(llm, intent=...)`) y genera. Es el patrón del framework.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from livekit.agents import AgentSession
from livekit.plugins import anthropic
from pydantic import ValidationError

from ops_agent.agent import OpsAgent
from ops_agent.config import Settings
from ops_agent.deps import AgentDeps
from ops_agent.rag.index import load_corpus
from ops_agent.rag.retriever import Bm25Retriever
from ops_agent.tools.shipments import JsonShipmentRepository

# Mismo timeout explícito que el pipeline de producción (SPEC §6, estándares: toda llamada de
# red con timeout). 10 s para conectar, 30 s de lectura entre chunks del streaming.
_LLM_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


@pytest.fixture(scope="session")
def settings() -> Settings:
    """Config real desde `.env`. Sin clave real de Anthropic no hay eval posible: se salta.

    Dos formas de "no hay clave": el campo requerido ausente (ValidationError) o presente pero
    vacío en el `.env` (placeholder). En ambas se salta para que `uv run pytest` quede verde en
    CI/headless sin credenciales, en vez de reventar dentro del plugin.
    """
    try:
        loaded = Settings()  # type: ignore[call-arg]  # BaseSettings carga del entorno/.env
    except ValidationError as exc:
        pytest.skip(f"Evals requieren credenciales en .env (no cargadas): {exc}")
    if not loaded.anthropic_api_key.get_secret_value():
        pytest.skip("Evals requieren ANTHROPIC_API_KEY con valor en .env (está vacía).")
    return loaded


@pytest.fixture(scope="session")
def deps(settings: Settings) -> AgentDeps:
    """Dependencias deterministas: dataset fijo de envíos + retriever léxico offline."""
    return AgentDeps(
        shipments=JsonShipmentRepository(),
        retriever=Bm25Retriever(load_corpus()),
        settings=settings,
    )


@pytest.fixture
def eval_llm(settings: Settings) -> anthropic.LLM:
    """LLM real de Anthropic, con timeout explícito. Genera las respuestas y juzga los intents.

    Función-scoped a propósito: cada test recibe un cliente ligado a su propio event loop
    (pytest-asyncio crea uno por test), evitando reusar un cliente atado a un loop ya cerrado.
    """
    return anthropic.LLM(
        model=settings.claude_model,
        api_key=settings.anthropic_api_key.get_secret_value(),
        timeout=_LLM_TIMEOUT,
    )


@pytest_asyncio.fixture
async def session(
    deps: AgentDeps, eval_llm: anthropic.LLM
) -> AsyncIterator[AgentSession[AgentDeps]]:
    """Sesión de texto con el `OpsAgent` real ya arrancado. Sin audio, sin room."""
    async with AgentSession[AgentDeps](llm=eval_llm, userdata=deps) as sess:
        await sess.start(OpsAgent())
        yield sess
