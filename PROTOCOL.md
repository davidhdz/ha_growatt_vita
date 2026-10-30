# Growatt portable power station — BLE protocol (reverse-engineered)

Device under test: **Growatt VITA 500 PRO**
- BLE name `XXXXXXFFXXXX`, MAC `9C:9E:6E:XX:XX:XX`
- WiFi module MAC `9C:9E:6E:XX:XX:XX` (Espressif, no open TCP ports)
- datalog SN reported by the device: `0JARXXXXXX`

Source: decompiled MyGro APK (`com.growatt.mygro`). Everything below is **validated against
the decompiled code AND against live BLE traffic** from this device.

The app talks to this device through **protocol version 7 (AES-CBC)** — *not* version 5 (XOR).
Proof: the reply to the BLE-key handshake is `00 18 00 07 00 0F 01 18 …`, i.e. `reply[3] == 0x07`
(`CmdUtils.getProtocolVersion` → `reply[3]==7 ? 7 : 5`).

The matching app presenter is **`PowerDevice2000ProPresenter`** (device profile "INFINITY 2000 PRO"
family). Its v7 poll loop reads regs **0..124** then **125..215**, which is exactly what this
device answers (125 regs, then 91 regs). The older `VitaPowerDevicePresenter` is v5-only and does
**not** apply here.

Scope of this document: **read-only** (FC3/FC4). Write commands (FC6) are listed for completeness.

---

## 1. GATT

| Item | UUID |
|---|---|
| Service | `000000FF-0000-1000-8000-00805f9b34fb` |
| RX/TX (write + notify) | `0000ff01-0000-1000-8000-00805f9b34fb` |
| FF02 | `0000ff02-…` (read) |
| FF03 | `0000ff03-…` (write, write-without-response) |
| FF04 | `0000ff04-…` (write, write-without-response) — firmware/file |
| 1801/2a05 | indicate |
| 1800/2aa6,2a00,2a01 | read (device info) |

- Advertised name `XXXXXXFFXXXX`. Not bonded.
- Enable notifications on `ff01`; write requests to `ff01` with **response = True**.
- There is **no app-level BLE password** (`InputBlePwdDialog`/`SettingBlePwdDialog` are dead code).
  The only gate is the **BLE key** (§3).
- The very first notification is a 15-byte init/hello packet
  `00 01 02 03 04 05 06 07 08 09 0A 0B 0C 0D 0E` — ignore it (fails the outer CRC / AES).
- The device stops advertising while connected; disconnect before reconnecting.
- Do **not** mix v5 and v7 frames in one session — it triggers `UNLIKELY_ERROR` and drops the link.

## 2. Session flow

1. Connect GATT, discover FF00, enable notifications on FF01.
2. **Send BLE key** with `Protocol0X18.newInstance(54, "growatt_iot_device_common_key_01")`.
   - `54` = `Param.ParamNoConstant.PARAM_NO_SECRET_KEY`.
   - Reply: `protocolVersion = (reply[3] == 7) ? 7 : 5`; success when `plain[12] == 0`.
   - The device echoes datalog SN `0JARXXXXXX` in the reply.
3. **Poll loop** (`PowerDevice2000ProPresenter`):
   - send `04_1` = FC4 read `start=0, count=125`  → reply → `Data04`
   - send `04_2` = FC4 read `start=125, count=91` → reply → `Data05`
   - repeat, ~1.5 s between cycles.

## 3. Transport framing (v7, `Protocol0X17`)

### 3.1 Request / reply wire layout

```
offset  bytes  field
0..1    2      totalLength      = frame_len - 2            (big-endian)
2..3    2      protocolVersion  = 00 07
4..5    2      dataLength       = len(modbusData) + 14     (big-endian)
6       1      deviceAddress    = 01
7       1      funCode          = 0x17 (modbus) / 0x18 / 0x19
8..     K      AES area         (AES/CBC/NoPadding, length % 16 == 0)
end-2.. 2      CRC16 over bytes [0 .. frame_len-3]         (big-endian)
```

- `totalLength = dataLength + 4 + zeroPad + 2`, where `zeroPad = (-(len(modbusData)+12)) % 16`.
- For an FC4 read request: `len(modbusData)=8` → `zeroPad=12` → `dataLength=22` → `totalLength=40`
  → wire frame length **42**.

### 3.2 AES

```
AES/CBC/NoPadding   key = b"growatt_aes16key"   iv = b"growatt_aes16Ivs"
```

Plaintext placed in the AES area = `dataArea`:

```
dataArea = datalogSn(10, "0000000000") || modbusLen(2, BE) || modbusData || zeroPad
```

### 3.3 Modbus RTU frame (inside `modbusData`)

```
[ slave=01 ][ funCode ][ startAddr(2) ][ count/val(2) ][ CRC(2) ]    # CRC low byte first
```

- FC3 / FC4 read: field `count` = number of registers.
- FC6 write single: field = value.

### 3.4 Response decode (`Protocol.getDecodeDataArea`, `Protocol0X17.getModbusData`)

```
if crc16(verify, big-endian) ok:
    plain      = AES_dec( raw[8 : len(raw)-2] )      # includes datalogSn + len + modbus + pad
    modbusLen  = int(plain[10:12], BE)
    modbus     = plain[12 : 12+modbusLen]            # slave, fun, byteCount, data, crc
    byteCount  = modbus[2]
    regs       = modbus[3 : 3+byteCount]             # 2 bytes/register, big-endian
```

- **Register N = `plain[15 + 2N]`** (`= modbus[3 + 2N]`).
- FC6 reply: success when `modbus[2]`/value as per Modbus.
- 0x18 reply (settings/key): success when `plain[12] == 0`.

## 4. Register map

Values are big-endian 16-bit; `/10` where noted. `int32 = (hi<<16)|lo` for 32-bit fields.

### 4.1 Main block `04_1` (FC4, regs 0..124) — `Data04`

| Reg | Field | Scale | Notes |
|----:|-------|------:|-------|
| 0   | powerStatus        | –   | operating state (see §5) |
| 3–4 | solarEnergy        | /10 | 32-bit; PV/car input power (W) |
| 5   | dcValue            | /10 | DC (12 V) output power (W) |
| 8   | usbOutEn           | –   | **USB output on/off (v7 state)** |
| 9–10| acValue            | /10 | 32-bit; AC output power (W) |
| 11  | acSwitchStatus     | –   | **AC output on/off (v7 state)**; R129 mirrors |
| 12  | usbSwitchStatus    | –   | v5 only — getter has no v7 branch; use R8 |
| 16  | totalBatterySoc    | –   | % |
| 18  | soc                | –   | % (primary) |
| 26  | temperature        | /10 | °C (signed, `byte2Temperature`) |
| 30  | chargeTime         | –   | min (-1 / 0xFFFF = n/a) |
| 31  | availableTime      | –   | estimated remaining runtime (min); 65535 = n/a on grid (see §4.3) |
| 36–37| acVoltage         | /10 | 32-bit; **AC charging power (W)** — battery charge power drawn from AC. Misnamed getter (`getAcVoltage`). Fills the app *Input* page AC tile. Verified in the field: ~500 W while charging, tapers near full, then 0 when the battery is full even though grid pass-through continues. NOT a voltage. |
| 38  | totalChargeTime    | –   | total remaining charge time |
| 39  | totalAvailableTime | –   | estimated remaining runtime (min); 65535 on grid (see §4.3) |
| 40  | fault              | –   | fault code (0 = none) |
| 41–43| warningNum         | –   | 6 bytes / 48-bit warning bitmap |
| 55  | usb1               | /10 | USB-A 1 (W) |
| 56  | usb2               | /10 | USB-A 2 (W) |
| 57  | usb3 / fastCharge  | /10 | USB-A 3 (W) |
| 58  | usbC1              | /10 | USB-C 1 (W) |
| 59  | usbC2              | /10 | USB-C 2 (W) |
| 61  | inputTotal         | –   | total AC/grid input power (W) = AC charge (R36/37) + pass-through to load |
| 62  | outputTotal        | –   | total output power (W) |
| 63  | usb4               | /10 | USB (W) |
| 66  | wlan               | /10 | |
| 93  | brightnessProgress | –   | v5 only — no v7 branch |
| 95  | ledStatus          | –   | v5 only — no v7 branch (real v7 LED status is R144, see §6.2) |
| 96  | boostStatus        | –   | v5 only — no v7 branch |
| 98  | dcCigarStatus      | –   | v5 only — no v7 branch; use R126 |

### 4.2 Extended block `04_2` (FC4, regs 125..215) — `Data05`

Add-on-battery / parallel fields are zero on this unit. `R125`/`R126` are live:
`R126` carries the **12 V DC output state (v7)** while `R125` (Watt+) stays 0.
Offset `o` maps to reg `125 + (o-15)/2`.

| Reg | Field | Notes |
|----:|-------|-------|
| 125 | WattPlusEn | 0 always on this unit (Watt+ state not readable) |
| 126 | DC_12V_STATUS | **12 V DC output on/off (v7 state)** |
| 127 | BatAutoHeatEn | battery auto-heat |
| 128 | HEAT_TIME | |
| 129 | UPS_STATUS | |
| 131 | CARAVAN_VALUE | |
| 143 | ledBrightnessLevel | light intensity (0 = off, 100 = steady, 500 = flashing) |
| 144 | ledStatus (v7) | **emergency LED light mode (v7 state)**: 0 = off, 1 = steady, 2 = flashing/SOS |
| 155 | ParallelStatus | |
| 156 | US240VacOutputStatus | |
| 157 | ParallelTotalCapacity | |
| 158 | ParallelTotalInputPwr | |
| 159 | ParallelTotalOutputPwr | |
| 160 | ParallelTotalSoc | |
| 185 | EbmCarOutEn | add-on pack: car output |
| 186 | EbmUsbOutEn | add-on pack: USB output |
| 187 | EbmPackQuantity | add-on pack count |
| 188 | EbmOrderNum | |
| 189 | EbmSoc | add-on pack SOC |
| 190 | EbmInputPwr | |
| 191 | EbmOutputPwr | |
| 192 | EbmCellTempMax | |
| 193 | EbmInputAdapterChgPwr | |
| 194 | EbmCarOutputPwr | |
| 195–200 | EbmUsbFastChg1..4 / UsbC1..2 OutputPwr | |
| 201 | EbmBatAutoHeatStatus | |
| 202 | EbmBatAutoHeatRemainTime | |
| 203 | EbmChgRemainTime | |
| 204 | EbmDisChgRemainTime | |
| 205 | EbmWarnStatus | |
| 206 | EbmFaultStatus | |
| 207 | EbmInputAdapterStatus | |

> No cumulative kWh counter is exposed over BLE in `Data*`. The Energy Dashboard must be fed by
> integrating the instantaneous power sensors (Riemann sum) or from the cloud API.

### 4.3 Empirically mapped registers (live experiments)

Method: full `04_1`/`04_2` snapshots in controlled states — LED off/steady/flashing,
grid plugged/unplugged, and AC output toggled on/off via FC6 (R0) — plus a 150 s
passive time-series. Toggling the output isolates load-dependent registers; unplugging
the grid isolates input-side registers.

**Input vs output separation** (drop to 0 when the grid is unplugged, restore when plugged):

| Reg | Meaning | Scale | Evidence |
|----:|---------|-------|----------|
| 20 | **AC input voltage** | /10 V | 115–116 V on grid, **0 unplugged**, unaffected by the output toggle |
| 21 | **AC input frequency** | /100 Hz | 6000 (60.00 Hz) on grid, **0 unplugged** |
| 22 | **AC output voltage** | /10 V | 115 V on, **0 when output off or unit off** |
| 23 | **AC output frequency** | /100 Hz | 59–60 Hz on, **0 when output off** |

**Confirmed by the output toggle / grid plug-unplug / reset:**

| Reg | Meaning | Notes |
|----:|---------|-------|
| 0 | powerStatus | 0 = output off; 2 = running on battery; 10 = running on grid |
| 1 | status code | 9/10/11, tracks R0 (exact meaning unknown) |
| 25 | temperature-like | follows the output (≈36 off → 39 °C) |
| 26 | main temperature | /10 °C (documented in §4.1) |
| 31 | **remaining runtime** | min; **65535 = n/a on grid**, 387 on battery (≈6.5 h at 60 W) |
| 33 | temperature-like | follows the output (≈40 → 44) |
| 34 | AC-output power-ish | **0 when output off**; does not scale exactly with R10 |
| 35 | internal / unstable | jumps erratically across states (282…1225); not a physical value |
| 39 | total remaining runtime | mirrors R31 (65535 on grid) |
| 44 | constant | 30062 on this unit (meaning unknown) |
| 60 | input-side power | **0 without grid**; equals R61 |
| 61 | inputTotal | W; **0 without grid** |
| 62 | outputTotal | W; stays non-zero on battery while R60/R61 drop to 0 |
| 68 | status word | 0 (output off) / 1–2 (running) / 29 (on battery) |
| 70 | duplicate of R9/R10 | AC output power high word |
| 74 | internal | **0 on grid, 820 on battery** (meaning unknown) |
| 84 | status word | state-dependent (1/2 running, 31 on battery; 30000 seen transient) |
| 129 | AC-output/status | mirrors R11 (1 on / 0 off) |
| 132 | grid presence | 2 on grid, 0 unplugged |

> Corrections to §4.1/§5: R31/R39 are the **estimated remaining runtime (min)**, not a fixed
> clock — they read `65535` when on grid. R60/R61 are **input-side** power (0 without grid)
> while R62 is output-side; they coincide only when input is present and the battery is not
> charging. R21 is the **input** frequency (0 when unplugged), not a nominal constant.
> R35 and R74 are internal/unstable and should not be surfaced as sensors.

## 5. Reference live capture

`04_1` (regs 0..124) from `9C:9E:6E:XX:XX:XX`, one sample:

```
R0  powerStatus        = 2
R1                     = 11
R9,R10 acValue         = 450   -> 45.0 W
R11 acSwitchStatus     = 1
R12 usbSwitchStatus    = 0
R16 totalBatterySoc    = 63
R18 soc                = 63  %
R26 temperature        = 340 -> 34.0 °C
R30 chargeTime         = 65535 (-1)
R31 availableTime      = 302
R38 totalChargeTime    = 65535 (-1)
R39 totalAvailableTime = 302
R40 fault              = 0
R41–43 warnings        = 0
R55–59 usb              = 0
R61 inputTotal         = 0
R62 outputTotal        = 45
R93/95/96/98           = 0
```

`04_2` (regs 125..215): `R126` (DC state), `R129` (AC-output status), `R143`/`R144`
(LED) are live; the rest are 0 on this unit (see §4.2, §4.3, §6.2).

Power-state values seen: `0` (output off), `2` (running on battery), `10` (running on grid).

## 6. Other queries / commands

| Purpose | v7 frame |
|---|---|
| Battery-protect progress | FC4 read reg 15 (`getBatteryProtectProgress`) |
| All settings (FC3) | FC3 read regs 0..107 (`newInstanceFor0X03(0,108)`) |
| Single SOC | FC4 read reg 18, count 1 |
| Setting codes (FC6 reg #) | `BleSettingCodes`: CHARGE_AC_RATE 44, BUZZING 107, STANDBY_TIME 16, HOLDING 17, FACTORY_RESET 33, AC_SHUTDOWN 87, USB_SHUTDOWN 78, DC_SHUTDOWN 79, CAR_INPUT 92, SCREEN_SCHEDULING 105, DC_OUTPUT_MODEL 98, USB_OUTPUT_MODE 102, AC_OUTPUT_MODEL 97 |
| Writes (FC6, later) | acSwitch R0, screenRestTime R17, dcSwitch R51, cigarEn R55, ledBrightness R83, ledState R85, powerBoostEn R86 |

### 6.1 Control writes — VERIFIED (FC6), toggle semantics

This unit follows the **`OutPut2000ProPresenter`** register set. The critical
finding: **an FC6 write to a control register toggles the output regardless of
the written value** (probed with 256, 0, 1 and 2 — all just flip the state). The
app writes 256/0 but the firmware ignores the value and toggles. Therefore a
correct integration must read the state register first and only write when the
desired state differs.

| Output | Write reg | State reg (v7) | Result |
|--------|----------:|---------------:|--------|
| AC output | 0 | 11 (129 mirrors) | toggles AC; value ignored |
| USB output | 80 | 8 (`usbOutEn`) | toggles USB; **R51 from the Vita550 map does NOT work here** |
| DC / 12 V car | 90 (R55 also works) | 126 (`DC_12V_STATUS`) | toggles DC |
| Power boost (Watt+) | 89 (R86 also works) | **none readable** | write toggles, but no state reg found (R96/R125 stay 0) |

State propagation: the state register only reflects the new value **~2 s after**
the write; reads during that window return the stale value. An integration must
wait ~2.5 s (or poll later) before trusting the read-back.

Register aliasing: the device accepts both the 2000Pro and Vita550 register
numbers for DC (90/55) and boost (89/86); for USB only R80 works (R51 does not).

### 6.2 Emergency LED light — status only (no known write)

The front emergency LED has **three modes**, cycled by the physical button:
**off → steady → flashing/SOS**. The mode is readable over BLE at **R144**
(0/1/2), with **R143** carrying a correlated intensity (0/100/500). Confirmed by
snapshotting the full register block in each physical state (off / steady /
flashing).

The state is **read-only**: writing R144 or R143 returns a Modbus exception
(`FC 0x86`, code `0x01` ILLEGAL FUNCTION). The Vita550 write registers
(`ledState` R85, `ledBrightness` R83) are **also rejected** with the exact same
`0x86 0x01` ILLEGAL-FUNCTION frame, while a known-writable control (AC R0)
returns the normal FC6 echo — i.e. the firmware whitelists writable registers and
R83/R85 are not in it (they have **no physical effect** on this unit). The APK
builds those writes with the identical FC6 path used for the working outputs
(`ModbusUtil.modbusPro(6, reg, val)`), so the official app could not drive the
lamp on this unit either. The MyGro app exposes no lamp control for
the 2000Pro profile either (the Vita550-only `switchLed`→R85 path, plus
`bLightLumi`→R105 which is the *screen* light). A blind FC6 sweep over regs
0..31 left R2, R5, R6, R7, R8, R16, R17, R19, R31 writable but then hung the
BLE link and dropped the AC output (recovered only by a physical power-cycle) —
**do not brute-force scan write registers**.

The integration therefore exposes **R144 read-only** (enum sensor
`emergency_light`: `off`/`steady`/`flashing`). Driving the light over BLE is an
open item (no write register identified; the APK exposes none for this profile).


## 7. Encoder reference

`vita7.py` / `run_dump.py` (this dir + `/tmp/opencode`) implement the encoder/decoder in Python
and reproduce the device traffic above. Self-test: round-tripping a built FC4 request decrypts to
`0000000000 || 0008 || 01 04 0000 007D <crc>`.

## 8. Open items

- Exact `powerStatus` enum names (values observed: 0, 2).
- `solarEnergy` vs `acValue` labelling: the fragment shows `getSolarEnergy` on the "car/PV" tile
  and `getAcValue` as the main output tile; confirm against the app UI.
- `acVoltage` (R36/37): RESOLVED — it is **AC charging power (W)**, not a voltage. Field data:
  0 W idle, ramp to ~500 W during a charge session (14:45–15:23), taper at top, then 0 W when full.
  Meanwhile `inputTotal` (R61) = R36/37 + pass-through load (e.g. 562 = 502 + 60).
- AC **output** voltage is now exposed: **R22** (see §4.3), and output frequency at R23.
- Register mapping largely resolved in §4.3: R20/R21 = AC input V/Hz, R22/R23 = AC output V/Hz,
  R31/R39 = remaining runtime, R60/R61 = input power, R62 = output power, R70 = duplicate output
  power. Still unclear: R1 (status), R17 (drifting counter), R25/R33 (temperature-like), R35 and
  R74 (internal/unstable), R44 (const 30062), R68/R84 (status words).
- **Power-boost state is not exposed**: R96/R125 stay 0 no matter the writes (R86/R89), so the
  integration drives it as an optimistic (last-command) switch.
- **MyGro app crash (details screen)**: `VitaOutPutFragment` calls `getBleData()` (`Data04`)
  getters `getUsbSwitchStatus`/`getDcCigarStatus`/`getLedStatus`/`getBoostStatus`/
  `getBrightnessProgress`; none have a v7 branch, so in v7 they read the null v5 buffer → NPE.
