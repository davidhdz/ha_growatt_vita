"""Switch platform for the Growatt portable power station (BLE)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import SWITCHES, SwitchDescription
from .coordinator import GrowattVitaCoordinator
from .entity import GrowattVitaEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: GrowattVitaCoordinator = entry.runtime_data
    async_add_entities(GrowattVitaSwitch(coordinator, desc) for desc in SWITCHES)


class GrowattVitaSwitch(GrowattVitaEntity, SwitchEntity):
    """A controllable on/off output."""

    def __init__(
        self, coordinator: GrowattVitaCoordinator, desc: SwitchDescription
    ) -> None:
        super().__init__(coordinator, desc.key)
        self._desc = desc
        self._attr_name = desc.name
        if desc.icon is not None:
            self._attr_icon = desc.icon

    @property
    def is_on(self) -> bool | None:
        return self._data.get(self._desc.key)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_switch_set(self._desc, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_switch_set(self._desc, False)
