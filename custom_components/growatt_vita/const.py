"""Constants for the Growatt portable power station (BLE) integration."""

from __future__ import annotations

from dataclasses import dataclass

DOMAIN = "growatt_vita"

MANUFACTURER = "Growatt"
MODEL = "Portable Power Station"

DEFAULT_NAME = "Growatt Power Station"
DEFAULT_POLL_INTERVAL = 30

CONF_ADDRESS = "address"

# GATT
SERVICE_UUID = "000000ff-0000-1000-8000-00805f9b34fb"
CHAR_RX_TX_UUID = "0000ff01-0000-1000-8000-00805f9b34fb"

# Protocol v7 crypto
AES_KEY = b"growatt_aes16key"
AES_IV = b"growatt_aes16Ivs"
DATALOG_SN = b"0000000000"
DEVICE_ADDRESS = 0x01
SECRET_KEY_PARAM_NO = 54
SECRET_KEY_VALUE = b"growatt_iot_device_common_key_01"


@dataclass(frozen=True)
class SensorDescription:
    """Describes a read-only sensor backed by a register."""

    key: str
    register: int
    name: str
    device_class: str | None = None
    state_class: str | None = None
    unit: str | None = None
    scale: float = 1.0
    word_count: int = 1
    icon: str | None = None
    value_map: dict[int, str] | None = None


@dataclass(frozen=True)
class SwitchDescription:
    """Describes a controllable on/off output.

    The device treats an FC6 write to ``register`` as a *toggle* (the written
    value is ignored), so the switch reads ``state_register`` first and only
    writes when the desired state differs.  ``state_register`` is ``None`` when
    the state cannot be read back over BLE (the switch is then optimistic).
    """

    key: str
    register: int
    on_value: int
    state_register: int | None
    name: str
    icon: str | None = None


@dataclass(frozen=True)
class EnergyDescription:
    """Describes a computed energy (kWh) sensor derived from power sensors.

    The device exposes no kWh register, so energy is obtained by integrating
    one or more power sensors over time.  ``source_keys`` are the keys of the
    power sensors in the coordinator data; when more than one is given their
    values are summed (e.g. all USB ports).
    """

    key: str
    source_keys: tuple[str, ...]
    name: str
    icon: str | None = None


# field -> register. reg N = plain[15 + 2N]; Data04/Data05 reference.
SENSORS: tuple[SensorDescription, ...] = (
    SensorDescription("soc", 18, "Battery", "battery", None, "%", scale=1.0, word_count=1),
    SensorDescription(
        "temperature", 26, "Temperature", "temperature", "measurement", "°C", scale=0.1
    ),
    SensorDescription(
        "input_power", 61, "Input power", "power", "measurement", "W", scale=1.0
    ),
    SensorDescription(
        "output_power", 62, "Output power", "power", "measurement", "W", scale=1.0
    ),
    # Registers mapped empirically (see growatt-vita-re/PROTOCOL.md §4.3).
    SensorDescription(
        "ac_input_voltage", 20, "AC input voltage", "voltage", "measurement", "V", scale=0.1
    ),
    SensorDescription(
        "ac_input_frequency", 21, "AC input frequency", "frequency", "measurement", "Hz",
        scale=0.01,
    ),
    SensorDescription(
        "ac_output_voltage", 22, "AC output voltage", "voltage", "measurement", "V", scale=0.1
    ),
    SensorDescription(
        "ac_output_frequency", 23, "AC output frequency", "frequency", "measurement", "Hz", scale=0.01
    ),
    SensorDescription(
        "remaining_time",
        31,
        "Remaining runtime",
        "duration",
        "measurement",
        "h",
        scale=1 / 60,
        icon="mdi:timer-sand",
    ),
    SensorDescription(
        "ac_output_power", 9, "AC output power", "power", "measurement", "W",
        scale=0.1, word_count=2, icon="mdi:power-plug",
    ),
    SensorDescription(
        "dc_output_power", 5, "DC output power", "power", "measurement", "W", scale=0.1
    ),
    SensorDescription(
        "solar_input_power", 3, "Solar/car input power", "power", "measurement", "W",
        scale=0.1, word_count=2, icon="mdi:solar-power",
    ),
    SensorDescription(
        "ac_input_power", 36, "AC charging power", "power", "measurement", "W",
        scale=0.1, word_count=2, icon="mdi:battery-charging",
    ),
    SensorDescription(
        "usb1_power", 55, "USB-A 1 power", "power", "measurement", "W", scale=0.1
    ),
    SensorDescription(
        "usb2_power", 56, "USB-A 2 power", "power", "measurement", "W", scale=0.1
    ),
    SensorDescription(
        "usb3_power", 57, "USB-A 3 power", "power", "measurement", "W", scale=0.1
    ),
    SensorDescription(
        "usb4_power", 63, "USB-A 4 power", "power", "measurement", "W", scale=0.1
    ),
    SensorDescription(
        "usbc1_power", 58, "USB-C 1 power", "power", "measurement", "W", scale=0.1
    ),
    SensorDescription(
        "usbc2_power", 59, "USB-C 2 power", "power", "measurement", "W", scale=0.1
    ),
    SensorDescription("fault", 40, "Fault code", icon="mdi:alert", scale=1),
    SensorDescription("warning_count", 41, "Warnings", icon="mdi:alert-outline"),
    # Emergency LED light mode.  Read-only: on this unit the light is driven by
    # the physical button; reg 144 (0=off, 1=steady, 2=flashing) is status only
    # (writes are rejected with a Modbus exception).  Confirmed live.
    SensorDescription(
        "light_mode",
        144,
        "Emergency light",
        icon="mdi:lightbulb",
        value_map={0: "off", 1: "steady", 2: "flashing"},
    ),
)

# Time the device needs to propagate a toggle before the state register
# reflects it (measured ~2 s; transient reads during this window are stale).
SWITCH_SETTLE_SECONDS = 2.5

# Control registers (Modbus FC6), from OutPut2000ProPresenter (this unit's
# profile). Writes are TOGGLES: the value is ignored, so the entity reads the
# state register and only writes when a change is needed. Confirmed live.
SWITCHES: tuple[SwitchDescription, ...] = (
    SwitchDescription("ac_output", 0, 256, 11, "AC output", "mdi:power-plug"),
    SwitchDescription("usb_output", 80, 1, 8, "USB output", "mdi:usb"),
    SwitchDescription("dc_output", 90, 1, 126, "DC output", "mdi:car-power"),
    SwitchDescription("watt_plus", 89, 1, None, "Power boost", "mdi:flash"),
)

# The device has no kWh register, so energy is integrated from power.  A single
# integration step is only taken when the elapsed time is at most this many
# seconds; longer gaps (HA stopped, BLE outage) are skipped so they do not
# produce a false jump in the accumulated energy.
MAX_ENERGY_GAP_SECONDS = 90.0

ENERGY_SENSORS: tuple[EnergyDescription, ...] = (
    EnergyDescription(
        "ac_output_energy",
        ("ac_output_power",),
        "AC output energy",
        icon="mdi:transmission-tower-export",
    ),
    EnergyDescription(
        "ac_input_energy",
        ("ac_input_power",),
        "AC input energy",
        icon="mdi:transmission-tower-import",
    ),
    EnergyDescription(
        "solar_input_energy",
        ("solar_input_power",),
        "Solar input energy",
        icon="mdi:solar-power-variant",
    ),
    EnergyDescription(
        "dc_output_energy",
        ("dc_output_power",),
        "DC output energy",
        icon="mdi:car-power",
    ),
    EnergyDescription(
        "usb_energy",
        (
            "usb1_power",
            "usb2_power",
            "usb3_power",
            "usb4_power",
            "usbc1_power",
            "usbc2_power",
        ),
        "USB energy",
        icon="mdi:usb",
    ),
)
