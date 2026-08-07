"""Function tools expuestas al LLM (borde fino acoplado a LiveKit).

Responsabilidad (fase de implementación):
    `@function_tool` con `RunContext[AgentDeps]`:
    - `lookup_shipment(shipment_id)`: consulta el repositorio de envíos.
    - `search_docs(query)`: recupera del corpus vía el Retriever (aplica umbral).
    - `end_call()`: cierre de la conversación.

Andamiaje: sin implementar todavía.
"""
