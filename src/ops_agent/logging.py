"""Logging estructurado con structlog + redacción de secretos.

Objetivos de esta capa:

- **Un solo formato** para todo: los logs propios (structlog) y los de LiveKit y sus
  plugins (que usan el `logging` estándar) se enrutan por la MISMA cadena de procesadores
  vía ``ProcessorFormatter`` (el puente stdlib↔structlog). Así nada se sale del formato.
- **Redacción de secretos**: un procesador borra el valor de cualquier campo cuyo nombre
  sugiera un secreto (api_key, token, secret…) y de cualquier ``SecretStr`` que se cuele
  en un evento, antes de que llegue al render. Complementa el enmascarado de ``SecretStr``.
- **Sin segunda frontera con el entorno**: aquí no se lee `os.environ`; el nivel y el
  formato los decide quien llama (normalmente ``agent.py`` a partir de la config). La única
  frontera con el entorno es :mod:`ops_agent.config`.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Mapping
from typing import Any

import structlog
from pydantic import SecretStr

# Subcadenas que, en el nombre de un campo, delatan un secreto. Comparación en minúsculas.
_SENSITIVE_HINTS = (
    "api_key",
    "apikey",
    "secret",
    "token",
    "password",
    "passwd",
    "authorization",
)
_REDACTED = "«redacted»"


def _redact_secrets(
    _logger: object, _method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Borra valores sensibles del evento por nombre de campo o por tipo ``SecretStr``.

    Va en la cadena de ambos caminos (structlog y logs foráneos de LiveKit), así que un
    secreto pasado por `extra=` o dentro del propio mensaje estructurado nunca se renderiza.
    """
    for key, value in event_dict.items():
        if isinstance(value, SecretStr):
            event_dict[key] = _REDACTED
            continue
        lowered = key.lower()
        if any(hint in lowered for hint in _SENSITIVE_HINTS):
            event_dict[key] = _REDACTED
    return event_dict


def configure_logging(*, json_logs: bool = False, level: str = "INFO") -> None:
    """Configura structlog y enruta el logging estándar (LiveKit) por la misma cadena.

    Args:
        json_logs: JSON por línea (para producción / agregadores) vs consola legible.
        level: nivel raíz por nombre ("DEBUG", "INFO", …).

    Idempotente: reemplaza los handlers del logger raíz, así que llamarla dos veces no
    duplica salida.
    """
    level_num = logging.getLevelNamesMapping().get(level.upper(), logging.INFO)
    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)

    # Procesadores que ven TODOS los eventos, vengan de structlog o de logging estándar.
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.ExtraAdder(),
        _redact_secrets,
        timestamper,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            *shared_processors,
            # Entrega el evento al ProcessorFormatter del handler stdlib para el render final.
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    renderer: Any = (
        structlog.processors.JSONRenderer()
        if json_logs
        else structlog.dev.ConsoleRenderer(colors=not json_logs)
    )
    formatter = structlog.stdlib.ProcessorFormatter(
        # foreign_pre_chain procesa los logs que NO nacen en structlog (LiveKit, urllib3…).
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level_num)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Logger estructurado ya configurado. Usar en vez de ``logging.getLogger``."""
    return structlog.stdlib.get_logger(name)


def redact_event(event_dict: Mapping[str, Any]) -> dict[str, Any]:
    """Aplica la redacción a un dict suelto (útil en tests). No muta el original."""
    return _redact_secrets(None, "info", dict(event_dict))


__all__ = ["configure_logging", "get_logger", "redact_event"]
