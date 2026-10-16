"""Low-level v7 (AES) BLE protocol codec for Growatt portable power stations.

Validated against live traffic from a Growatt VITA 500 PRO (see
``growatt-vita-re/PROTOCOL.md``). Builds FC3/FC4 reads and FC6 single-register
writes.

This module intentionally has no Home Assistant / bleak dependency so it can be
unit-tested on its own.
"""

from __future__ import annotations

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from .const import (
    AES_IV,
    AES_KEY,
    DATALOG_SN,
    DEVICE_ADDRESS,
    SECRET_KEY_PARAM_NO,
    SECRET_KEY_VALUE,
)

FUN_MODBUS = 0x17
FUN_SETTING = 0x18

# Modbus function codes inside the payload
FC_READ = 0x04
FC_READ_HOLDING = 0x03
FC_WRITE = 0x06


def crc16(data: bytes) -> int:
    """Modbus CRC16 (poly 0xA001, init 0xFFFF)."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc & 0xFFFF


def _i2b(value: int) -> bytes:
    return bytes([(value >> 8) & 0xFF, value & 0xFF])


def _aes_encrypt(data: bytes) -> bytes:
    enc = Cipher(algorithms.AES(AES_KEY), modes.CBC(AES_IV)).encryptor()
    return enc.update(data) + enc.finalize()


def _aes_decrypt(data: bytes) -> bytes:
    dec = Cipher(algorithms.AES(AES_KEY), modes.CBC(AES_IV)).decryptor()
    return dec.update(data) + dec.finalize()


def _modbus_read(fc: int, start: int, count: int) -> bytes:
    body = bytes([DEVICE_ADDRESS, fc]) + _i2b(start) + _i2b(count)
    crc = crc16(body)
    return body + bytes([crc & 0xFF, crc >> 8])


def _wrap(fun_code: int, modbus: bytes, data_length: int) -> bytes:
    """Wrap a Modbus payload in a v7 frame (AES area + big-endian CRC)."""
    length = len(modbus)
    pad = (-(length + 12)) % 16
    data_area = DATALOG_SN + _i2b(length) + modbus + b"\x00" * pad
    aes = _aes_encrypt(data_area)
    body = (
        _i2b(8 + len(aes))
        + b"\x00\x07"
        + _i2b(data_length)
        + bytes([DEVICE_ADDRESS, fun_code])
        + aes
    )
    return body + _i2b(crc16(body))


def build_read(fc: int, start: int, count: int) -> bytes:
    """Build a v7 FC3/FC4 read request."""
    modbus = _modbus_read(fc, start, count)
    return _wrap(FUN_MODBUS, modbus, len(modbus) + 14)


def _modbus_write_fc06(register: int, value: int) -> bytes:
    body = bytes([DEVICE_ADDRESS, FC_WRITE]) + _i2b(register) + _i2b(value & 0xFFFF)
    crc = crc16(body)
    return body + bytes([crc & 0xFF, crc >> 8])


def build_write_fc06(register: int, value: int) -> bytes:
    """Build a v7 FC6 (write single register) request."""
    modbus = _modbus_write_fc06(register, value)
    return _wrap(FUN_MODBUS, modbus, len(modbus) + 14)


def build_key_request() -> bytes:
    """Build the v7 BLE-key handshake request (0x18, param 54)."""
    bean = _i2b(SECRET_KEY_PARAM_NO) + _i2b(len(SECRET_KEY_VALUE)) + SECRET_KEY_VALUE
    pad = (-(len(bean) + 14)) % 16
    data_area = DATALOG_SN + _i2b(1) + _i2b(len(bean)) + bean + b"\x00" * pad
    aes = _aes_encrypt(data_area)
    body = (
        _i2b(8 + len(aes))
        + b"\x00\x07"
        + _i2b(len(bean) + 16)
        + bytes([DEVICE_ADDRESS, FUN_SETTING])
        + aes
    )
    return body + _i2b(crc16(body))


def decode_plain(frame: bytes) -> bytes | None:
    """Verify the outer CRC and return the AES-decrypted data area."""
    if len(frame) < 10:
        return None
    if frame[-2:] != _i2b(crc16(frame[:-2])):
        return None
    try:
        return _aes_decrypt(frame[8:-2])
    except ValueError:
        return None


def decode_registers(frame: bytes) -> list[int] | None:
    """Decode an FC3/FC4 read reply into a list of 16-bit register values."""
    plain = decode_plain(frame)
    if plain is None:
        return None
    if plain[13] not in (FC_READ_HOLDING, FC_READ):
        return None
    modbus_len = int.from_bytes(plain[10:12], "big")
    modbus = plain[12 : 12 + modbus_len]
    if len(modbus) < 3:
        return None
    byte_count = modbus[2]
    data = modbus[3 : 3 + byte_count]
    return [int.from_bytes(data[i : i + 2], "big") for i in range(0, len(data) - 1, 2)]


def decode_write_reply(frame: bytes) -> tuple[int, int] | None:
    """Decode an FC6 write reply into the echoed (register, value) pair.

    A Modbus FC6 reply echoes the request: ``[addr][06][reg hi][reg lo]
    [value hi][value lo][crc]``. Returns None if it is not an FC6 reply.
    """
    plain = decode_plain(frame)
    if plain is None or len(plain) < 18:
        return None
    if plain[13] != FC_WRITE:
        return None
    register = int.from_bytes(plain[14:16], "big")
    value = int.from_bytes(plain[16:18], "big")
    return register, value


def decode_key_success(frame: bytes) -> bool | None:
    """Return True/False for a 0x18 key reply, or None if it can't be decoded."""
    plain = decode_plain(frame)
    if plain is None:
        return None
    return plain[12] == 0


def datalog_sn(frame: bytes) -> str | None:
    """Return the datalog SN echoed in a reply, if decodable."""
    plain = decode_plain(frame)
    if plain is None:
        return None
    return plain[0:10].decode("ascii", "ignore")


def fun_code(frame: bytes) -> int | None:
    if len(frame) < 8:
        return None
    return frame[7]
