# Changelog

All notable changes to this project are documented in this file.

## [0.2.1] - 2026-10-30

### Added

- CI workflow running hassfest and the HACS validation action.
- `icon@2x.png` (512×512) alongside the standard integration icon.

### Changed

- Brand icon optimized (800×800 16-bit → 256×256 8-bit) for faster loading.
- Device identifiers in `PROTOCOL.md` (MAC addresses, BLE name and serial)
  redacted.

### Fixed

- `manifest.json` keys sorted as required by hassfest.
- Removed `cryptography` from `requirements`: it is already provided by Home
  Assistant and must not be listed by a custom integration.

## [0.2.0] - 2026-10-29

### Added

- Energy counters (kWh) computed by integrating the power sensors over time:
  AC output, AC input, solar input, DC output and USB.
- `RestoreSensor`-backed accumulation: values survive Home Assistant restarts.
- Gaps longer than 90 s (HA stopped, BLE outage) are skipped so they do not
  create false jumps in the accumulated energy.

### Changed

- Remaining runtime is now exposed in hours (`h`) so Home Assistant renders it
  as `Xh Ym` (e.g. `6h 27m`) instead of a raw minute count.

## [0.1.0] - 2026-10-15

### Added

- Initial release.
- BLE (v7 AES) transport with automatic Bluetooth discovery.
- Read-only sensors: battery SoC, temperature, AC/DC/USB/solar power, AC input
  and output voltage/frequency, remaining runtime, fault/warning flags and the
  emergency-LED mode.
- Switches for the AC, USB and DC outputs plus Power boost (Watt+).
- Config flow (Bluetooth discovery + manual MAC address entry).
