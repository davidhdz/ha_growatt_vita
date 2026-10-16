"""DataUpdateCoordinator for the Growatt portable power station (BLE)."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .ble import GrowattVitaClient
from .const import (
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    SENSORS,
    SWITCHES,
    SWITCH_SETTLE_SECONDS,
    SensorDescription,
    SwitchDescription,
)

_LOGGER = logging.getLogger(__name__)

# App poll loop reads regs 0..124 (`04_1`) then 125..215 (`04_2`). The second
# block holds the DC output state (reg 126), so both are read.
MAIN_BLOCK_START = 0
MAIN_BLOCK_COUNT = 125


def _extract(regs: list[int], desc: SensorDescription) -> float | None:
    if desc.register + desc.word_count > len(regs):
        return None
    if desc.word_count == 2:
        value = (regs[desc.register] << 16) | regs[desc.register + 1]
    else:
        value = regs[desc.register]
    if value == 0xFFFF:
        return None
    return value * desc.scale


def _popcount(*words: int) -> int:
    count = 0
    for word in words:
        count += bin(word).count("1")
    return count


class GrowattVitaCoordinator(DataUpdateCoordinator[dict[str, float | bool | None]]):
    """Polls a Growatt power station over BLE."""

    def __init__(self, hass: HomeAssistant, address: str) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} {address}",
            update_interval=timedelta(seconds=DEFAULT_POLL_INTERVAL),
        )
        self.address = address
        self._client = GrowattVitaClient(hass, address)

    async def _async_update_data(self) -> dict[str, float | bool | None]:
        try:
            regs = await self._client.async_read_all()
        except Exception as err:  # noqa: BLE001
            await self._client.async_disconnect()
            raise UpdateFailed(f"BLE read failed: {err}") from err

        data: dict[str, float | bool | None] = {}
        for desc in SENSORS:
            data[desc.key] = _extract(regs, desc)

        # Warning count = popcount of the 48-bit warning bitmap (regs 41..43).
        data["warning_count"] = _popcount(regs[41], regs[42], regs[43])

        previous = self.data or {}
        for desc in SWITCHES:
            if desc.state_register is not None and desc.state_register < len(regs):
                data[desc.key] = bool(regs[desc.state_register])
            else:
                # No read-back available: keep the last (optimistic) state.
                data[desc.key] = previous.get(desc.key, False)

        return data

    async def async_switch_set(self, desc: SwitchDescription, turn_on: bool) -> None:
        """Toggle the output if needed, then refresh.

        The device toggles on any FC6 write, so the current state is read first
        and the write is skipped when it already matches ``turn_on``.
        """
        wrote = await self._client.async_set_switch(
            desc.register, desc.on_value, desc.state_register, turn_on
        )
        if self.data is not None:
            self.data[desc.key] = turn_on
            self.async_set_updated_data(self.data)
        if wrote:
            # The state register only reflects the toggle after ~2 s; refresh
            # too early and the stale value would overwrite the optimistic one.
            await asyncio.sleep(SWITCH_SETTLE_SECONDS)
        await self.async_request_refresh()

    async def async_shutdown(self) -> None:
        await self._client.async_disconnect()
        await super().async_shutdown()
