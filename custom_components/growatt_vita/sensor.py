"""Sensor platform for the Growatt portable power station (BLE)."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import SENSORS, SensorDescription
from .coordinator import GrowattVitaCoordinator
from .entity import GrowattVitaEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: GrowattVitaCoordinator = entry.runtime_data
    async_add_entities(
        GrowattVitaSensor(coordinator, desc) for desc in SENSORS
    )


class GrowattVitaSensor(GrowattVitaEntity, SensorEntity):
    """A read-only register-backed sensor."""

    def __init__(self, coordinator: GrowattVitaCoordinator, desc: SensorDescription) -> None:
        super().__init__(coordinator, desc.key)
        self._key = desc.key
        self._value_map = desc.value_map
        self._attr_name = desc.name
        if desc.device_class is not None:
            self._attr_device_class = SensorDeviceClass(desc.device_class)
        if desc.value_map is not None:
            self._attr_device_class = SensorDeviceClass.ENUM
            self._attr_options = list(desc.value_map.values())
        if desc.state_class is not None:
            self._attr_state_class = SensorStateClass(desc.state_class)
        if desc.unit is not None:
            self._attr_native_unit_of_measurement = desc.unit
        if desc.icon is not None:
            self._attr_icon = desc.icon

    @property
    def native_value(self) -> float | str | None:
        value = self._data.get(self._key)
        if self._value_map is not None and value is not None:
            return self._value_map.get(int(value))
        return value
