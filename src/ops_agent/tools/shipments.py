"""Envíos: modelo de dominio y repositorio (sin acoplar a LiveKit).

Esta capa no importa nada de LiveKit: es dominio puro y testeable en aislamiento.

- ``Shipment`` (modelo pydantic, inmutable y con ``extra="forbid"``): valida el dataset
  en el arranque, así una errata en el JSON (un ``status`` inexistente, un campo de más)
  falla al cargar con contexto en vez de colarse hasta la conversación.
- ``ShipmentStatus``: los cinco estados posibles como ``Literal`` — único sitio donde
  vive el vocabulario de estados, junto a su etiqueta legible para leer en voz alta.
- ``ShipmentRepository`` (Protocol) con ``.get(id) -> Shipment | None``: contrato que las
  tools consumen sin conocer el origen de los datos (hoy JSON, mañana Supabase).
- ``JsonShipmentRepository``: carga ``data/shipments.json`` una vez al construirse y sirve
  lookups en memoria (sin red, sin I/O por consulta), insensibles a mayúsculas/espacios.

``get`` devuelve ``None`` cuando el envío no existe: la tool lo traduce a un mensaje de
"no encontrado" y el agente lo comunica sin inventar (criterio 4).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, ValidationError

ShipmentStatus = Literal[
    "in_transit",
    "out_for_delivery",
    "delivered",
    "exception",
    "customs_hold",
]

# Human-readable label for speech synthesis: avoids the TTS reading "out underscore for
# underscore delivery".
_STATUS_LABELS: dict[ShipmentStatus, str] = {
    "in_transit": "in transit",
    "out_for_delivery": "out for delivery",
    "delivered": "delivered",
    "exception": "delayed by an incident",
    "customs_hold": "held in customs",
}

# El dataset vive en la raíz del repo (data/), no dentro del paquete. Se resuelve desde la
# ubicación de este fichero: .../src/ops_agent/tools/shipments.py -> parents[3] = raíz.
DEFAULT_SHIPMENTS_PATH = Path(__file__).resolve().parents[3] / "data" / "shipments.json"


class Shipment(BaseModel):
    """Un envío del dataset fijo. Inmutable: es un valor, no una entidad mutable."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    shipment_id: str
    status: ShipmentStatus
    location: str
    eta: str
    carrier: str
    last_update: str

    @property
    def status_label(self) -> str:
        """Natural-language status for reading aloud."""
        return _STATUS_LABELS[self.status]


class ShipmentRepository(Protocol):
    """Fuente de envíos. Las tools dependen de este contrato, no de la implementación."""

    def get(self, shipment_id: str) -> Shipment | None:
        """Devuelve el envío por su identificador, o ``None`` si no existe."""
        ...


def _normalize(shipment_id: str) -> str:
    """Clave canónica para el lookup: sin espacios y en mayúsculas.

    Da igual cómo formatee el identificador el LLM ("shp-1024", " SHP-1024 "): se resuelve
    al mismo envío. Robustez necesaria en un pipeline de voz.
    """
    return shipment_id.strip().upper()


def _load_shipments(path: Path) -> dict[str, Shipment]:
    """Carga y valida el dataset. Cualquier fallo se propaga con contexto (qué y dónde)."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"No se pudo leer el dataset de envíos en {path}") from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"El dataset de envíos {path} no es JSON válido") from exc

    if not isinstance(data, dict):
        raise RuntimeError(
            f"El dataset de envíos {path} debe ser un objeto keyed por id, "
            f"no {type(data).__name__}."
        )

    by_id: dict[str, Shipment] = {}
    for key, value in data.items():
        try:
            shipment = Shipment.model_validate(value)
        except ValidationError as exc:
            raise RuntimeError(f"Envío inválido bajo la clave {key!r} en {path}") from exc
        # La clave y el shipment_id del valor deben coincidir: si no, el dataset miente
        # sobre sí mismo y un lookup por clave devolvería un envío con otro id.
        if _normalize(shipment.shipment_id) != _normalize(key):
            raise RuntimeError(
                f"Inconsistencia en {path}: la clave {key!r} no coincide con "
                f"shipment_id {shipment.shipment_id!r}."
            )
        by_id[_normalize(key)] = shipment
    return by_id


class JsonShipmentRepository:
    """Repositorio en memoria respaldado por un JSON keyed por id, cargado al construirse."""

    def __init__(self, path: Path = DEFAULT_SHIPMENTS_PATH) -> None:
        self._by_id = _load_shipments(path)

    def get(self, shipment_id: str) -> Shipment | None:
        return self._by_id.get(_normalize(shipment_id))


__all__ = [
    "DEFAULT_SHIPMENTS_PATH",
    "JsonShipmentRepository",
    "Shipment",
    "ShipmentRepository",
    "ShipmentStatus",
]
