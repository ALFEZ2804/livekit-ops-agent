"""Tools del agente y su capa de datos.

- ``shipments``: modelo de dominio + repositorio de envíos (sin imports de LiveKit).
- ``agent_tools``: las ``@function_tool`` (borde fino acoplado a LiveKit).

Este ``__init__`` no reexporta nada a propósito: importar desde ``ops_agent.tools`` no debe
arrastrar ``agent_tools`` (que importa ``deps``, que a su vez importa ``tools.shipments``),
para no crear un ciclo de imports. Cada consumidor importa por su ruta explícita:
``ops_agent.tools.shipments`` para el dominio, ``ops_agent.tools.agent_tools`` para las tools.
"""
