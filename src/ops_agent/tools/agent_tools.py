"""Function tools exposed to the LLM (thin edge coupled to LiveKit).

Each tool receives ``RunContext[AgentDeps]``: LiveKit injects that context and excludes it
from the schema the model sees, so the LLM only sees the domain arguments. Each tool's name
and description come from its docstring (that's what the model reads to decide when to call
it), which is why they are written for the model.

This module implements ``lookup_shipment`` (order lookup), ``search_docs`` (RAG over the
internal documentation) and ``end_call`` (hang up).

The tools are NOT registered here: they are defined as functions and the wiring layer passes
them to ``OpsAgent(tools=[...])`` together with ``AgentDeps`` as the session ``userdata``.
"""

from __future__ import annotations

import asyncio

from livekit.agents import RunContext, function_tool

from ..deps import AgentDeps
from ..logging import get_logger
from ..rag.retriever import select_relevant

_log = get_logger("ops_agent.tools")


@function_tool
async def lookup_shipment(context: RunContext[AgentDeps], shipment_id: str) -> str:
    """Look up the status, location and estimated delivery time (ETA) of an order.

    Use it whenever someone asks about a specific order. Do not make up the status: answer
    with what this tool returns.

    Args:
        shipment_id: the order number, a four-digit code, for example 1024.
    """
    shipment = context.userdata.shipments.get(shipment_id)

    if shipment is None:
        _log.info("lookup_shipment", shipment_id=shipment_id, found=False)
        return (
            f"There is no order with the number {shipment_id}. "
            "It's worth double-checking the number with the caller."
        )

    _log.info(
        "lookup_shipment",
        shipment_id=shipment.shipment_id,
        found=True,
        status=shipment.status,
    )
    return (
        f"Order {shipment.shipment_id}. "
        f"Status: {shipment.status_label}. "
        f"Location: {shipment.location}. "
        f"ETA: {shipment.eta}. "
        f"Carrier: {shipment.carrier}. "
        f"Last update: {shipment.last_update}."
    )


@function_tool
async def search_docs(context: RunContext[AgentDeps], query: str) -> str:
    """Search Nordport's internal procedures and policy documentation.

    Use it for procedure or policy questions: failed deliveries, how to reschedule a
    delivery, delivery times and windows, and returns. Answer ONLY with the text this tool
    returns; if it returns nothing, say you don't have that information instead of making it
    up.

    Args:
        query: the question or topic to search for, in natural language.
    """
    # Retrieval (ONNX embedding on CPU) is blocking; it is offloaded to a thread so it does
    # not freeze the event loop while the voice pipeline stays alive.
    chunks = await asyncio.to_thread(select_relevant, context.userdata.retriever, query, 3)

    if not chunks:
        _log.info("search_docs", query=query, hits=0)
        return (
            "There is no information about that in Nordport's internal documentation. "
            "It's best to say that information isn't available."
        )

    _log.info("search_docs", query=query, hits=len(chunks), docs=[c.doc_id for c in chunks])
    passages = "\n\n---\n\n".join(chunk.text for chunk in chunks)
    return (
        "Passages retrieved from the internal documentation. Answer based only on this "
        f"content:\n\n{passages}"
    )


@function_tool
async def end_call(context: RunContext[AgentDeps]) -> None:
    """End the call when the person says goodbye or confirms they don't need anything else.

    Do not use it to pause or to change topic: only to close the conversation.
    """
    # Let the goodbye finish playing before closing the session: closing now would cut the
    # current turn's TTS off mid-sentence.
    await context.wait_for_playout()
    await context.session.aclose()


__all__ = ["end_call", "lookup_shipment", "search_docs"]
