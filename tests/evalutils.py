"""Ayudas para los asserts deterministas de las evals.

El framework de LiveKit expone `RunResult.events` (secuencia cronológica de lo ocurrido en
el turno: mensajes, llamadas a tool y sus outputs). `expect()` cubre "existe una llamada a
la tool X" y el juicio de un mensaje; estas funciones cubren lo que `expect()` no da con
comodidad:

- la **lista** de tools invocadas (para asserts negativos, p. ej. "no llamó a
  lookup_shipment"),
- el **texto** de los outputs de tool (para comprobar campos exactos por subcadena, ya que
  `is_function_call_output(output=...)` exige igualdad literal), y
- el **índice del último mensaje del asistente**, para juzgar la respuesta final del turno
  sin asumir que es el último evento (podría haber un evento de tool detrás).
"""

from __future__ import annotations

from typing import Any

from livekit.agents.voice.run_result import (
    ChatMessageEvent,
    FunctionCallEvent,
    FunctionCallOutputEvent,
    RunResult,
)

# Los helpers solo leen ``result.events``, que no depende del parámetro genérico de salida;
# ``RunResult[Any]`` acepta cualquier instanciación (RunResult[None], etc.) sin chocar con la
# invarianza de genéricos.


def tool_call_names(result: RunResult[Any]) -> list[str]:
    """Nombres de las function tools invocadas en el turno, en orden."""
    return [ev.item.name for ev in result.events if isinstance(ev, FunctionCallEvent)]


def tool_call_outputs(result: RunResult[Any]) -> list[str]:
    """Textos devueltos por las function tools en el turno, en orden."""
    return [
        ev.item.output
        for ev in result.events
        if isinstance(ev, FunctionCallOutputEvent) and isinstance(ev.item.output, str)
    ]


def last_assistant_index(result: RunResult[Any]) -> int:
    """Índice en ``result.events`` del último mensaje del asistente (la respuesta final).

    Robusto frente a eventos de tool posteriores a un preámbulo hablado: se queda con el
    último mensaje de rol ``assistant``. Falla con contexto si el agente no respondió.
    """
    index: int | None = None
    for i, ev in enumerate(result.events):
        if isinstance(ev, ChatMessageEvent) and ev.item.role == "assistant":
            index = i
    if index is None:
        raise AssertionError("El agente no produjo ningún mensaje de asistente en el turno.")
    return index
