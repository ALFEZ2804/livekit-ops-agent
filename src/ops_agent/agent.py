"""Punto de entrada de la CLI y ÚNICA capa acoplada a LiveKit.

El mismo `agent.py` corre en `console` (fase 1, sin credenciales de LiveKit Cloud) y en
`dev` / `start` (fase 2, con credenciales) sin cambios de código: solo cambia el
subcomando y la presencia de las variables `LIVEKIT_*`.

Andamiaje: `entrypoint` se limita a conectar a la room y avisar de que la sesión de voz
todavía no está cableada. Los plugins (STT/LLM/TTS/VAD + turn detector), el `OpsAgent` y
el `AgentSession` con sus métricas se construyen en la fase de implementación.
"""

from __future__ import annotations

import logging

from livekit.agents import JobContext, WorkerOptions, cli

logger = logging.getLogger("ops_agent")


async def entrypoint(ctx: JobContext) -> None:
    """Job entrypoint. Andamiaje: conecta y no arranca `AgentSession` todavía."""
    await ctx.connect()
    logger.info("ops-agent: andamiaje activo; la sesion de voz aun no esta implementada")


def main() -> None:
    """CLI de LiveKit Agents: subcomandos `console` / `dev` / `start` / `download-files`."""
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))


if __name__ == "__main__":
    main()
