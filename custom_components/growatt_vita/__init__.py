"""The Growatt portable power station (BLE) integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import GrowattVitaCoordinator

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.SWITCH,
]

GrowattVitaConfigEntry = ConfigEntry[GrowattVitaCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: GrowattVitaConfigEntry) -> bool:
    """Set up Growatt Power Station from a config entry."""
    coordinator = GrowattVitaCoordinator(hass, entry.data["address"])
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: GrowattVitaConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.async_shutdown()
    return unload_ok
