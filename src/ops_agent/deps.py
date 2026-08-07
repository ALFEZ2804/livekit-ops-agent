"""Dependencias de sesión inyectadas en las tools (userdata).

``AgentDeps`` es el contenedor que se coloca como ``userdata`` del ``AgentSession``; las
tools lo reciben tipado vía ``RunContext[AgentDeps]`` y leen de él el repositorio, la
config y (cuando exista) el retriever, sin tocar el entorno ni globals.

Es inmutable a propósito: las dependencias se resuelven una vez al arrancar la sesión y
no cambian durante la llamada.
"""

from __future__ import annotations

from dataclasses import dataclass

from .config import Settings
from .rag.retriever import Retriever
from .tools.shipments import ShipmentRepository


@dataclass(frozen=True)
class AgentDeps:
    """Dependencias por sesión que consumen las function tools."""

    shipments: ShipmentRepository
    retriever: Retriever
    settings: Settings


__all__ = ["AgentDeps"]
