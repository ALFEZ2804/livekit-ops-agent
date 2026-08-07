"""Unit: shipment repository.

Covers the contract the tools rely on: an existing id returns a full ``Shipment``
(criterion 3), a missing id returns ``None`` so the tool answers "not found" without
inventing (criterion 4), the lookup is space-insensitive, and a corrupt dataset fails to load
with context instead of degrading silently.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ops_agent.tools.shipments import (
    DEFAULT_SHIPMENTS_PATH,
    JsonShipmentRepository,
    Shipment,
)


@pytest.fixture
def repo() -> JsonShipmentRepository:
    return JsonShipmentRepository(DEFAULT_SHIPMENTS_PATH)


def test_get_existing_returns_full_shipment(repo: JsonShipmentRepository) -> None:
    shipment = repo.get("1024")

    assert isinstance(shipment, Shipment)
    assert shipment.shipment_id == "1024"
    # Every field the tool reads aloud is populated.
    assert shipment.status_label
    assert shipment.location
    assert shipment.eta
    assert shipment.carrier
    assert shipment.last_update


def test_get_is_space_insensitive(repo: JsonShipmentRepository) -> None:
    assert repo.get("  1024  ") is not None
    assert repo.get("1024 ") is not None


def test_get_missing_returns_none(repo: JsonShipmentRepository) -> None:
    assert repo.get("0000") is None


def test_dataset_loads_all_statuses(repo: JsonShipmentRepository) -> None:
    # That the dataset loads without exception already proves each status validates against
    # the Literal; here we also check the human-readable label exists for all of them.
    for shipment_id in ("1024", "2070", "3120", "4088", "5200"):
        shipment = repo.get(shipment_id)
        assert shipment is not None
        assert shipment.status_label


def test_invalid_status_fails_to_load_with_context(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(
        '{"0001": {"shipment_id": "0001", "status": "nonexistent", '
        '"location": "x", "eta": "y", "carrier": "z", "last_update": "t"}}',
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="0001"):
        JsonShipmentRepository(bad)


def test_key_mismatch_fails_to_load(tmp_path: Path) -> None:
    bad = tmp_path / "mismatch.json"
    bad.write_text(
        '{"0001": {"shipment_id": "0002", "status": "delivered", '
        '"location": "x", "eta": "y", "carrier": "z", "last_update": "t"}}',
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="no coincide"):
        JsonShipmentRepository(bad)
