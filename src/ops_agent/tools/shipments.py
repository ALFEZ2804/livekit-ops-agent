"""Envíos: modelo de dominio y repositorio (sin acoplar a LiveKit).

Responsabilidad (fase de implementación):
    - `Shipment` (modelo pydantic): shipment_id, status
      ("en_transito"|"en_reparto"|"entregado"|"incidencia"|"retenido_aduana"),
      location, eta, carrier, last_update.
    - `ShipmentRepository` (Protocol) con `.get(id) -> Shipment | None`.
    - `JsonShipmentRepository`: carga `data/shipments.json` al arranque.

`None` => la tool devuelve "no encontrado" y el agente lo comunica sin inventar.

Andamiaje: sin implementar todavía.
"""
