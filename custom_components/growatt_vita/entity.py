"""Base entity for the Growatt portable power station (BLE)."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_ADDRESS, DOMAIN, MANUFACTURER, MODEL
from .coordinator import GrowattVitaCoordinator


class GrowattVitaEntity(CoordinatorEntity[GrowattVitaCoordinator]):
    """Base class for Growatt Power Station entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: GrowattVitaCoordinator, key: str) -> None:
        super().__init__(coordinator)
        address = coordinator.address
        self._attr_unique_id = f"{address}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, address)},
            name=f"Growatt Power Station {address}",
            manufacturer=MANUFACTURER,
            model=MODEL,
            connections={("bluetooth", address)},
            configuration_url=None,
        )

    @property
    def _data(self) -> dict:
        return self.coordinator.data or {}
