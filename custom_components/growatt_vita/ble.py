"""BLE client for the Growatt portable power station (v7 protocol)."""

from __future__ import annotations

import asyncio
import logging

from bleak import BleakClient
from bleak_retry_connector import establish_connection

from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant

from .const import CHAR_RX_TX_UUID
from .protocol import (
    FC_READ,
    FUN_MODBUS,
    FUN_SETTING,
    build_key_request,
    build_read,
    build_write_fc06,
    decode_key_success,
    decode_registers,
    decode_write_reply,
    fun_code,
)

_LOGGER = logging.getLogger(__name__)


class GrowattVitaClient:
    """Persistent BLE connection with a v7 handshake and frame queue."""

    def __init__(self, hass: HomeAssistant, address: str) -> None:
        self._hass = hass
        self._address = address
        self._client: BleakClient | None = None
        self._queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._lock = asyncio.Lock()
        self._key_ok = False

    def _on_notify(self, _sender, data: bytearray) -> None:
        frame = bytes(data)
        if len(frame) < 10:
            return
        self._queue.put_nowait(frame)

    async def _connect(self) -> None:
        ble_device = bluetooth.async_ble_device_from_address(
            self._hass, self._address, connectable=True
        )
        if ble_device is None:
            raise RuntimeError(f"Device {self._address} not found")
        self._client = await establish_connection(
            BleakClient, ble_device, self._address, max_attempts=3
        )
        self._queue = asyncio.Queue()
        await self._client.start_notify(CHAR_RX_TX_UUID, self._on_notify)
        self._key_ok = False

    async def async_disconnect(self) -> None:
        if self._client is not None:
            try:
                await self._client.disconnect()
            except Exception:  # noqa: BLE001
                pass
            self._client = None
        self._key_ok = False

    async def _send_and_wait(self, frame: bytes, expected_fun: int, timeout: float) -> bytes:
        assert self._client is not None
        # Drain stale frames (e.g. the 15-byte hello packet).
        while not self._queue.empty():
            self._queue.get_nowait()
        await self._client.write_gatt_char(CHAR_RX_TX_UUID, frame, response=True)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise TimeoutError("No reply from device")
            reply = await asyncio.wait_for(self._queue.get(), remaining)
            if fun_code(reply) == expected_fun:
                return reply

    async def _ensure_session(self) -> None:
        async with self._lock:
            if self._client is None or not self._client.is_connected:
                await self._connect()
            if not self._key_ok:
                reply = await self._send_and_wait(build_key_request(), FUN_SETTING, 5.0)
                if decode_key_success(reply) is not True:
                    raise RuntimeError("BLE key handshake failed")
                self._key_ok = True
                # The device emits a hello packet right after connecting; drop it.
                await asyncio.sleep(0.3)

    async def _read_block_locked(self, start: int, count: int) -> list[int]:
        frame = build_read(FC_READ, start, count)
        reply = await self._send_and_wait(frame, FUN_MODBUS, 5.0)
        regs = decode_registers(reply)
        if regs is None:
            raise RuntimeError("Malformed reply")
        return regs

    async def async_read_registers(self, start: int, count: int) -> list[int]:
        await self._ensure_session()
        async with self._lock:
            return await self._read_block_locked(start, count)

    async def async_read_all(self) -> list[int]:
        """Read the full BLE block: registers 0..124 then 125..215."""
        await self._ensure_session()
        async with self._lock:
            first = await self._read_block_locked(0, 125)
            second = await self._read_block_locked(125, 91)
        return first + second

    async def async_write_register(self, register: int, value: int) -> None:
        """Write a single holding register (Modbus FC6)."""
        await self._ensure_session()
        async with self._lock:
            frame = build_write_fc06(register, value)
            reply = await self._send_and_wait(frame, FUN_MODBUS, 5.0)
        echoed = decode_write_reply(reply)
        if echoed is None:
            raise RuntimeError("Malformed write reply")
        if echoed != (register, value & 0xFFFF):
            raise RuntimeError(f"Write not acknowledged: {echoed} != ({register}, {value})")

    async def async_set_switch(
        self,
        register: int,
        value: int,
        state_register: int | None,
        desired: bool,
    ) -> bool:
        """Toggle an output register, but only if it differs from ``desired``.

        The device toggles the output on any FC6 write (the value is ignored),
        so the current state is read first and the write is skipped when the
        state already matches.  When ``state_register`` is None the write is
        always performed (best effort, no read-back).  Returns True when a
        write was issued.
        """
        await self._ensure_session()
        async with self._lock:
            if state_register is not None:
                regs = await self._read_block_locked(state_register, 1)
                if bool(regs[0]) == desired:
                    return False
            frame = build_write_fc06(register, value)
            reply = await self._send_and_wait(frame, FUN_MODBUS, 5.0)
            echoed = decode_write_reply(reply)
            if echoed is None or echoed[0] != register:
                raise RuntimeError(f"Write not acknowledged: {echoed}")
            return True
