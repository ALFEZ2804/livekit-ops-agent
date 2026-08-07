"""Dependencias de sesión inyectadas en las tools (userdata).

Responsabilidad (fase de implementación):
    `AgentDeps` = { shipments: ShipmentRepository, retriever: Retriever,
    settings: Settings }. Se coloca como `userdata` del `AgentSession` y las tools
    lo reciben vía `RunContext[AgentDeps]`.

Andamiaje: sin implementar todavía.
"""
