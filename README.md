# Growatt Portable Power Station (BLE)

A Home Assistant custom integration for **Growatt portable power stations**
(VITA / Infinity series) that speak the **v7 AES BLE protocol** over the
`FF01`/`FF02` GATT service — no cloud, no dongle.

Reverse-engineered and validated against a **Growatt VITA 500 PRO**
(`INFINITY 2000 PRO` register profile). See [`PROTOCOL.md`](PROTOCOL.md) for the
full protocol write-up.

> ⚠️ The device accepts **only one BLE connection at a time**. While Home
> Assistant is connected the phone app cannot connect, and vice-versa.

## Features

- Local (BLE) polling, no cloud account required.
- Read-only sensors: battery SoC, temperature, AC/DC/USB/solar power, AC input
  & output voltage/frequency, remaining runtime, fault/warning flags and the
  emergency-LED mode.
- Energy counters (kWh) for AC output, AC input, solar input, DC output and
  USB, derived by integrating the power readings over time.
- Switches: AC output, USB output, DC / 12 V car output and Power boost (Watt+).

## Requirements

- Home Assistant 2024.10 or newer.
- A Bluetooth adapter reachable by HA (onboard, USB dongle or an ESPHome
  Bluetooth proxy).
- The power station must be powered on and within range.

## Installation

### HACS (recommended)

1. In HACS → **Integrations** → ⋮ → **Custom repositories**.
2. Add the URL of this repository, category **Integration**.
3. Install **Growatt Portable Power Station (BLE)** and restart Home Assistant.

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=davidhdz&repository=growatt_vita&category=integration)

### Manual

Copy the `custom_components/growatt_vita` folder into your HA `config`
directory and restart Home Assistant.

## Configuration

The device is auto-discovered over Bluetooth (`manufacturer_id 14919`).
Accept the discovered card, or add it manually via
**Settings → Devices & Services → Add Integration → Growatt Portable Power
Station (BLE)** and enter its Bluetooth (MAC) address.

## Entities

| Entity | Type | Register | Notes |
|--------|------|---------:|-------|
| Battery | sensor | 18 | State of charge, % |
| Temperature | sensor | 26 | °C |
| AC input voltage / frequency | sensor | 20 / 21 | V / Hz |
| AC output voltage / frequency | sensor | 22 / 23 | V / Hz |
| Input / Output power | sensor | 61 / 62 | W |
| AC output power | sensor | 9 | W (32-bit) |
| Solar / car input power | sensor | 3 | W (32-bit) |
| AC charging power | sensor | 36 | W (32-bit) |
| DC / USB-A / USB-C power | sensor | 5, 55-59, 63 | W |
| Remaining runtime | sensor | 31 | min (unknown while on grid) |
| Fault code / Warnings | sensor | 40 / 41-43 | |
| Emergency light | sensor | 144 | `off` / `steady` / `flashing` (read-only) |
| AC output | switch | 0 | state reg 11 |
| USB output | switch | 80 | state reg 8 |
| DC output | switch | 90 | state reg 126 |
| Power boost | switch | 89 | no read-back (optimistic) |
| AC output energy | sensor | ∫ 9 | kWh, computed |
| AC input energy | sensor | ∫ 36 | kWh, computed |
| Solar input energy | sensor | ∫ 3 | kWh, computed |
| DC output energy | sensor | ∫ 5 | kWh, computed |
| USB energy | sensor | ∫ 55-59, 63 | kWh, computed |

## Notes on control

The firmware treats an **FC6 write to a control register as a toggle** (the
written value is ignored), so the integration reads the state register first and
only writes when a change is needed.

The emergency LED is **status-only**: it is driven by the physical button, and
BLE writes to its registers are rejected by the firmware (Modbus exception
`0x86 0x01`).

## Energy dashboard

The device has no kWh register, so the integration derives energy by
integrating the power sensors over time (trapezoidal rule, 30 s polling). The
counters survive restarts and skip gaps longer than 90 s.

Suggested mapping in **Settings → Dashboards → Energy**:

| Dashboard field | Sensor |
|-----------------|--------|
| Solar production | `sensor..._solar_input_energy` |
| Grid consumption | `sensor..._ac_input_energy` (only when plugged into the grid) |
| Individual devices | `sensor..._ac_output_energy` (+ `_dc_output_energy` / `_usb_energy`) |

Do not use both the input and output counters as "consumption" at the same
time, or the dashboard will double-count.

## Disclaimer

This is an unofficial integration, not affiliated with Growatt. Use at your own
risk.
