"""Métricas por turno a partir de los eventos del ``AgentSession`` (API estable 1.6).

``MetricsReporter`` engancha los eventos que emite la sesión y produce, por cada turno de
conversación, UNA línea de log estructurado con la forma acordada::

    { turn_id, user_transcript, response, tool_calls,
      stt_ms, eou_delay_ms, llm_ttft_ms, tts_ttfb_ms, tokens }

Fuentes de datos (todo desde la superficie NO deprecada de livekit-agents 1.6; en esta
versión ``metrics_collected`` está marcado como deprecado a favor de ``ChatMessage.metrics``
para la latencia por turno y de ``session.usage`` para el uso acumulado):

- Latencia y textos vienen de ``conversation_item_added``. El ``ChatMessage`` de rol
  ``user`` ya trae en ``.metrics`` la ``transcription_delay`` (latencia REAL de la STT en
  streaming, donde ``STTMetrics.duration`` es siempre 0.0) y la ``end_of_turn_delay``; el de
  rol ``assistant`` trae ``llm_node_ttft`` y ``tts_node_ttfb``. Ambos se poblan antes de
  emitirse el evento, así que se leen directamente del item.
- Las tools ejecutadas vienen de ``function_tools_executed``.
- Los tokens del turno son el incremento del acumulado ``session.usage`` (el
  ``ModelUsageCollector`` de la sesión) entre el cierre de este turno y el del anterior; el
  acumulado total de la sesión se vuelca en ``log_summary``.

Correlación por frontera de turno: el turno se ABRE con el ``ChatMessage`` de usuario y se
CIERRA (se vuelca) cuando empieza el siguiente turno de usuario, o al cerrar la sesión. Por
eso una respuesta con preámbulo hablado + tool + respuesta final (varios mensajes de
asistente del MISMO turno lógico) produce UNA sola línea: solo hay un turno abierto a la vez
en un único slot (``self._open``), no un diccionario que pueda crecer sin cota ni volver a
volcar un turno ya emitido.

Punto de extensión (documentado, no implementado): estos mismos eventos son el sitio para
exportar spans a OpenTelemetry o traces a Langfuse; hoy solo se escriben a structlog.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from livekit.agents import (
    ConversationItemAddedEvent,
    FunctionToolsExecutedEvent,
)
from livekit.agents.llm import ChatMessage
from livekit.agents.metrics import LLMModelUsage, STTModelUsage, TTSModelUsage

from ..logging import get_logger

if TYPE_CHECKING:
    import structlog
    from livekit.agents import AgentSession


def _ms(seconds: float | None) -> float | None:
    """Segundos -> milisegundos redondeados. ``None`` se propaga (dato ausente)."""
    return round(seconds * 1000, 1) if seconds is not None else None


@dataclass
class _Turn:
    """Acumulador de las métricas de un turno mientras llegan sus eventos sueltos."""

    turn_id: str
    user_transcript: str | None = None
    response: str | None = None
    tool_calls: list[str] = field(default_factory=list)
    stt_ms: float | None = None
    eou_delay_ms: float | None = None
    llm_ttft_ms: float | None = None
    tts_ttfb_ms: float | None = None
    tokens: dict[str, int] | None = None


class MetricsReporter:
    """Engancha los eventos del ``AgentSession`` y registra métricas por turno.

    Uso::

        reporter = MetricsReporter()
        reporter.attach(session)
        ctx.add_shutdown_callback(reporter.log_summary)
    """

    def __init__(self, logger: structlog.stdlib.BoundLogger | None = None) -> None:
        self._log = logger or get_logger("ops_agent.metrics")
        self._session: AgentSession[Any] | None = None
        self._open: _Turn | None = None
        self._turn_seq = 0
        # Acumulado de tokens LLM ya volcado; el turno reporta el delta contra esto.
        self._counted_input = 0
        self._counted_output = 0

    def attach(self, session: AgentSession[Any]) -> None:
        """Registra los handlers en la sesión. Los callbacks del emisor son síncronos."""
        self._session = session
        session.on("conversation_item_added", self._on_conversation_item)
        session.on("function_tools_executed", self._on_tools_executed)

    async def log_summary(self) -> None:
        """Cierra el turno pendiente y vuelca el uso acumulado. Para ``add_shutdown_callback``."""
        self._flush()
        if self._session is None:
            return
        llm_input = llm_output = llm_cached = tts_chars = 0
        tts_audio = stt_audio = 0.0
        for usage in self._session.usage.model_usage:
            if isinstance(usage, LLMModelUsage):
                llm_input += usage.input_tokens
                llm_output += usage.output_tokens
                llm_cached += usage.input_cached_tokens
            elif isinstance(usage, TTSModelUsage):
                tts_chars += usage.characters_count
                tts_audio += usage.audio_duration
            elif isinstance(usage, STTModelUsage):
                stt_audio += usage.audio_duration
        self._log.info(
            "session_usage",
            llm_input_tokens=llm_input,
            llm_output_tokens=llm_output,
            llm_input_cached_tokens=llm_cached,
            tts_characters=tts_chars,
            tts_audio_seconds=round(tts_audio, 2),
            stt_audio_seconds=round(stt_audio, 2),
        )

    # --- Handlers de eventos -------------------------------------------------------

    def _on_conversation_item(self, ev: ConversationItemAddedEvent) -> None:
        item = ev.item
        if not isinstance(item, ChatMessage):
            return  # AgentHandoff u otros: no son turnos de conversación

        if item.role == "user":
            # Un mensaje de usuario abre turno: primero cierra el anterior (frontera de turno).
            self._flush()
            self._open = _Turn(
                turn_id=self._next_turn_id(),
                user_transcript=item.text_content,
                stt_ms=_ms(item.metrics.get("transcription_delay")),
                eou_delay_ms=_ms(item.metrics.get("end_of_turn_delay")),
            )
        elif item.role == "assistant":
            # El saludo inicial es una respuesta sin turno de usuario previo: abre uno.
            turn = self._open or _Turn(turn_id=self._next_turn_id())
            self._open = turn
            # Preámbulo + respuesta final comparten turno: la latencia es la del PRIMER
            # segmento (lo que percibe el usuario); el texto, el del ÚLTIMO (respuesta final).
            if turn.llm_ttft_ms is None:
                turn.llm_ttft_ms = _ms(item.metrics.get("llm_node_ttft"))
            if turn.tts_ttfb_ms is None:
                turn.tts_ttfb_ms = _ms(item.metrics.get("tts_node_ttfb"))
            turn.response = item.text_content

    def _on_tools_executed(self, ev: FunctionToolsExecutedEvent) -> None:
        if self._open is not None:
            self._open.tool_calls.extend(fc.name for fc in ev.function_calls)

    # --- Internos ------------------------------------------------------------------

    def _next_turn_id(self) -> str:
        self._turn_seq += 1
        return f"turn-{self._turn_seq}"

    def _token_delta(self) -> dict[str, int] | None:
        """Tokens del turno = incremento del acumulado LLM de la sesión desde el último volcado.

        Suma correctamente los turnos con varias llamadas al LLM (preámbulo + respuesta tras
        una tool). ``None`` si el turno no consumió LLM (p. ej. un turno de usuario sin réplica).
        """
        if self._session is None:
            return None
        total_input = total_output = 0
        for usage in self._session.usage.model_usage:
            if isinstance(usage, LLMModelUsage):
                total_input += usage.input_tokens
                total_output += usage.output_tokens
        prompt = total_input - self._counted_input
        completion = total_output - self._counted_output
        self._counted_input, self._counted_output = total_input, total_output
        if prompt == 0 and completion == 0:
            return None
        return {"prompt": prompt, "completion": completion, "total": prompt + completion}

    def _flush(self) -> None:
        """Vuelca el turno abierto (si lo hay) como una línea de log y libera el slot."""
        turn = self._open
        if turn is None:
            return
        self._open = None
        turn.tokens = self._token_delta()
        self._log.info(
            "turn",
            turn_id=turn.turn_id,
            user_transcript=turn.user_transcript,
            response=turn.response,
            tool_calls=turn.tool_calls or None,
            stt_ms=turn.stt_ms,
            eou_delay_ms=turn.eou_delay_ms,
            llm_ttft_ms=turn.llm_ttft_ms,
            tts_ttfb_ms=turn.tts_ttfb_ms,
            tokens=turn.tokens,
        )


__all__ = ["MetricsReporter"]
