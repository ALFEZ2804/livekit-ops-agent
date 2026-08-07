"""Agente de voz de operaciones sobre LiveKit Agents.

Paquete de aplicación. La única capa acoplada a LiveKit es :mod:`ops_agent.agent`;
el resto (config, tools, rag, observabilidad) se mantiene desacoplado tras Protocols
para poder testear sin audio ni credenciales de LiveKit Cloud.
"""

__version__ = "0.1.0"
