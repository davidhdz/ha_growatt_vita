# Changelog

All notable changes to this project are documented in this file.

## [0.2.0] - 2026-10-29

### Added

- Energy counters (kWh) computed by integrating the power sensors over time:
  AC output, AC input, solar input, DC output and USB.
- `RestoreSensor`-backed accumulation: values survive Home Assistant restarts.
- Gaps longer than 90 s (HA stopped, BLE outage) are skipped so they do not
  create false jumps in the accumulated energy.

## [0.1.0] - 2026-10-15

### Added

- Initial release.
- BLE (v7 AES) transport with automatic Bluetooth discovery.
- Read-only sensors: battery SoC, temperature, AC/DC/USB/solar power, AC input
  and output voltage/frequency, remaining runtime, fault/warning flags and the
  emergency-LED mode.
- Switches for the AC, USB and DC outputs plus Power boost (Watt+).
- Config flow (Bluetooth discovery + manual MAC address entry).
