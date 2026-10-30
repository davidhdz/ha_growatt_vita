"""Computed energy (kWh) sensors for the Growatt power station.

The device does not expose an energy register, so the energy counters are
obtained by integrating the power sensors over time (trapezoidal rule).  The
accumulated value is restored across restarts and long gaps are skipped.
"""

from __future__ import annotations

import time

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.core import callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ENERGY_SENSORS, MAX_ENERGY_GAP_SECONDS, EnergyDescription
from .coordinator import GrowattVitaCoordinator
from .entity import GrowattVitaEntity


def async_setup_energy(
    coordinator: GrowattVitaCoordinator,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create the computed energy sensors."""
    async_add_entities(
        GrowattVitaEnergySensor(coordinator, desc) for desc in ENERGY_SENSORS
    )


class GrowattVitaEnergySensor(GrowattVitaEntity, RestoreSensor):
    """Energy counter obtained by integrating power over time."""

    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = "kWh"
    _attr_suggested_display_precision = 3

    def __init__(
        self, coordinator: GrowattVitaCoordinator, desc: EnergyDescription
    ) -> None:
        super().__init__(coordinator, desc.key)
        self._desc = desc
        self._attr_name = desc.name
        if desc.icon is not None:
            self._attr_icon = desc.icon
        self._energy_wh = 0.0
        self._last_power: float | None = None
        self._last_time: float | None = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_sensor_data()
        if last is not None and last.native_value is not None:
            try:
                self._energy_wh = float(last.native_value) * 1000.0
            except (TypeError, ValueError):
                self._energy_wh = 0.0
        # Never integrate across the shutdown gap: seed on the next update.
        self._last_power = None
        self._last_time = None

    def _power(self) -> float | None:
        """Return the summed source power in W, or None if unavailable."""
        data = self.coordinator.data or {}
        values = [data.get(key) for key in self._desc.source_keys]
        if not values or any(value is None for value in values):
            return None
        return float(sum(values))

    @callback
    def _handle_coordinator_update(self) -> None:
        power = self._power()
        now = time.monotonic()
        if power is None or not self.coordinator.last_update_success:
            # Drop the baseline so a gap never produces a false jump.
            self._last_power = None
            self._last_time = None
        else:
            if self._last_power is not None and self._last_time is not None:
                elapsed = now - self._last_time
                if 0 < elapsed <= MAX_ENERGY_GAP_SECONDS:
                    average = (self._last_power + power) / 2.0
                    self._energy_wh += average * elapsed / 3600.0
            self._last_power = power
            self._last_time = now
        super()._handle_coordinator_update()

    @property
    def native_value(self) -> float:
        return round(self._energy_wh / 1000.0, 3)
