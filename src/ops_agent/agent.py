"""Punto de entrada de la CLI y ÚNICA capa acoplada a LiveKit.

El mismo `agent.py` corre en `console` (fase 1, sin credenciales de LiveKit Cloud) y en
`dev` / `start` (fase 2, con credenciales) sin cambios de código: solo cambia el subcomando
y la presencia de las variables `LIVEKIT_*`. La CLI de LiveKit expone además
`download-files`, que descarga los modelos locales (turn detector + Silero VAD) la primera
vez; ver README.

Este fichero arranca el pipeline de voz completo (STT -> LLM -> TTS + VAD + turn detector),
saluda al iniciar y registra métricas por turno. Aquí se engancha además el cableado de las
function tools (lookup_shipment / search_docs / end_call): se registran en `OpsAgent` y sus
dependencias (`AgentDeps`) se inyectan como `userdata` de la sesión, que es de donde las
tools las leen vía `RunContext[AgentDeps]`.
"""

from __future__ import annotations

import httpx
from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    JobProcess,
    WorkerOptions,
    cli,
)
from livekit.agents.vad import VAD
from livekit.plugins import anthropic, deepgram, elevenlabs, silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel

from .config import Settings
from .deps import AgentDeps
from .logging import configure_logging, get_logger
from .observability import MetricsReporter
from .prompts import GREETING_INSTRUCTIONS, SYSTEM_PROMPT
from .rag.index import load_corpus
from .rag.retriever import Bm25Retriever, EmbeddingRetriever, Retriever
from .tools.agent_tools import end_call, lookup_shipment, search_docs
from .tools.shipments import JsonShipmentRepository

# Timeout explícito de la llamada de generación al LLM (streaming): 10 s para conectar,
# 30 s de lectura entre chunks. Latencia baja sin colgar la conversación si Anthropic no
# responde. STT y TTS quedan acotados por el timeout de conexión que el AgentSession aplica
# por etapa (APIConnectOptions: 10 s + 3 reintentos por defecto), así que ninguna llamada de
# red del pipeline espera de forma indefinida.
_LLM_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


class OpsAgent(Agent):
    """Agente de operaciones: persona (SYSTEM_PROMPT) + sus tres function tools.

    Las tools se registran aquí, no dependen del entorno: sus dependencias (repo de envíos,
    retriever, settings) llegan por el ``userdata`` de la sesión (``AgentDeps``), que cada
    tool lee vía ``RunContext[AgentDeps]``. Es el mismo agente en console y en dev/start.
    """

    def __init__(self) -> None:
        super().__init__(
            instructions=SYSTEM_PROMPT,
            tools=[lookup_shipment, search_docs, end_call],
        )


def prewarm(proc: JobProcess) -> None:
    """Carga el modelo de VAD una sola vez por proceso, fuera del turno del usuario."""
    proc.userdata["vad"] = silero.VAD.load()


def _check_phase1_credentials(settings: Settings) -> None:
    """Falla pronto y con contexto si falta alguna credencial de proveedor de fase 1.

    Sin este chequeo, una clave vacía revienta más abajo dentro del plugin con un error
    opaco ("Deepgram API key is required"). Aquí se nombran todas las que faltan de una vez.
    """
    missing = [
        name
        for name, value in (
            ("DEEPGRAM_API_KEY", settings.deepgram_api_key.get_secret_value()),
            ("ANTHROPIC_API_KEY", settings.anthropic_api_key.get_secret_value()),
            ("ELEVENLABS_API_KEY", settings.elevenlabs_api_key.get_secret_value()),
            ("ELEVENLABS_VOICE_ID", settings.elevenlabs_voice_id),
            ("ELEVENLABS_MODEL", settings.elevenlabs_model),
        )
        if not value
    ]
    if missing:
        raise RuntimeError(
            "Faltan credenciales de fase 1 en el entorno/.env: "
            + ", ".join(missing)
            + ". Rellénalas en .env (plantilla en .env.example)."
        )


def _build_deps(settings: Settings) -> AgentDeps:
    """Compone las dependencias de sesión (repo de envíos + retriever + settings).

    El retriever por defecto en runtime es el de embeddings (fastembed, ONNX CPU). Si el
    modelo no está disponible (p. ej. primer arranque sin `download-files` y sin red), se
    degrada al retriever léxico BM25, que es determinista y no necesita red. La degradación
    se registra en log con el error para no perder el porqué; no se traga en silencio.
    """
    chunks = load_corpus()
    try:
        retriever: Retriever = EmbeddingRetriever(chunks)
    except Exception as exc:
        get_logger("ops_agent").warning("rag_embedding_fallback_bm25", error=str(exc))
        retriever = Bm25Retriever(chunks)
    return AgentDeps(
        shipments=JsonShipmentRepository(),
        retriever=retriever,
        settings=settings,
    )


def _build_session(settings: Settings, vad: VAD, deps: AgentDeps) -> AgentSession[AgentDeps]:
    """Construye el AgentSession con los plugins directos y las claves explícitas.

    Claves pasadas explícitas a cada plugin (no por env implícito): la única frontera con
    el entorno es `config.Settings`. Las dependencias de las tools viajan en ``userdata``.
    Barge-in queda activo por defecto (VAD + turn detector + interrupciones habilitadas),
    sin configuración extra.
    """
    return AgentSession(
        userdata=deps,
        stt=deepgram.STT(
            model="nova-3",
            language="en",  # English speech recognition
            api_key=settings.deepgram_api_key.get_secret_value(),
        ),
        llm=anthropic.LLM(
            model=settings.claude_model,
            api_key=settings.anthropic_api_key.get_secret_value(),
            timeout=_LLM_TIMEOUT,
        ),
        tts=elevenlabs.TTS(
            voice_id=settings.elevenlabs_voice_id,
            model=settings.elevenlabs_model,
            api_key=settings.elevenlabs_api_key.get_secret_value(),
        ),
        vad=vad,
        turn_detection=MultilingualModel(),  # modelo ONNX local (fase 1, sin gateway cloud)
    )


async def entrypoint(ctx: JobContext) -> None:
    """Job entrypoint: arranca la sesión de voz, saluda y engancha las métricas por turno."""
    configure_logging()
    log = get_logger("ops_agent")
    settings = Settings()  # type: ignore[call-arg]  # BaseSettings carga los campos del entorno
    _check_phase1_credentials(settings)

    vad = ctx.proc.userdata.get("vad") or silero.VAD.load()
    deps = _build_deps(settings)
    session = _build_session(settings, vad, deps)

    reporter = MetricsReporter()
    reporter.attach(session)
    ctx.add_shutdown_callback(reporter.log_summary)

    await ctx.connect()
    await session.start(OpsAgent(), room=ctx.room)
    log.info(
        "ops_agent_started",
        model=settings.claude_model,
        livekit_ready=settings.livekit_ready,
    )
    # Saludo inicial hablado (LLM -> TTS): ejercita el pipeline ya al arrancar.
    await session.generate_reply(instructions=GREETING_INSTRUCTIONS)


def main() -> None:
    """CLI de LiveKit Agents: subcomandos `console` / `dev` / `start` / `download-files`."""
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm))


if __name__ == "__main__":
    main()
