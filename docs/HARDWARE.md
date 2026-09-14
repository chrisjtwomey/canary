# Hardware reference — Inkplate 5 Gen2 environment monitor

Working shorthand for development, distilled from the datasheets. Every
section links its sources. Facts are from the datasheet unless marked
*(product page)*, *(schematic)*, *(derived)*, *(measured)*, *(bench)* or
*(unverified)*. Dates, and the history behind the text, are in the
[Decision Log](#decision-log).

- [0. At a glance](#0-at-a-glance)
- [1. Inkplate 5 Gen2](#1-inkplate-5-gen2)
- [2. SCD41 — CO₂](#2-scd41--co)
- [3. PMSA003I — particulates](#3-pmsa003i--particulates)
- [4. BME688 — VOC / gas, pressure](#4-bme688--voc--gas-pressure)
- [5. SHTC3 — temperature and humidity](#5-shtc3--temperature-and-humidity)
- [6. The I²C bus](#6-the-ic-bus)
- [7. Power](#7-power)
- [8. Wiring](#8-wiring)
- [9. The enclosure](#9-the-enclosure)
- [10. Open questions](#10-open-questions)
- [Decision Log](#decision-log)

---

## 0. At a glance

| Device | Board | I²C addr | Supply | Current, typical | Current, peak | Library |
|---|---|---|---|---|---|---|
| Inkplate 5 Gen2 | Soldered | host; 0x20 0x48 0x51 on board | USB-C 5 V or LiPo | 18 µA deep sleep *(product page)* | not published | Inkplate-Arduino-library ≥ 11.1 |
| SCD41 CO₂ | Adafruit 5190 | 0x62 | 2.4–5.5 V | 15 mA @ 5 s periodic; 0.45 mA single-shot every 5 min | **175 mA typ, 205 mA max** (3.3 V) | Sensirion I2C SCD4x |
| PMSA003I PM | Adafruit 4632 | 0x12 | 5 V module; board makes its own 5 V from 3–5 V | ≤ 100 mA @ 5 V → **~200 mA from 3.3 V** *(derived)* | 250 mA / 100 ms fan start *(charge pump rating)* | Adafruit PM25AQI |
| BME688 gas | Soldered 333203 | 0x76 (JP1 → 0x77) | 1.7–3.6 V (board takes 3.3–5 V) | 0.9 mA (BSEC LP), 0.09 mA (ULP) | 17 mA heater | Bosch BME68x + BSEC2 |
| SHTC3 T/RH | Soldered 333032 | 0x70 fixed | 1.62–3.6 V (board takes 3.3–5 V) | 430 µA measuring, 0.3 µA sleep | 0.9 mA | Adafruit_SHTC3 |

**Bus:** no address conflicts. Five sets of 10 kΩ pull-ups in parallel = 2.0 kΩ,
within spec at 100 kHz (the Inkplate library's default). All four connector
systems (easyC, Qwiic, STEMMA QT) are the same JST-SH 4-pin in the same order.

**Power verdict:** the Inkplate's 3.3 V regulator is 500 mA and also runs the
ESP32. Sensor peaks alone reach ~470 mA. **Power the sensor chain from its own
3.3 V regulator, fed from the Inkplate's VIN pad (5 V when on USB).** Details
in §7.

---

## 1. Inkplate 5 Gen2

Sources: [product page](https://soldered.com/products/inkplate-5-gen2) ·
[docs](https://docs.soldered.com/inkplate/5v2/overview/) ·
[hardware repo (KiCad, schematic PDF, BOM, STEP, STL)](https://github.com/SolderedElectronics/Soldered-Inkplate-5-Gen2-hardware-design) ·
[Arduino library](https://github.com/SolderedElectronics/Inkplate-Arduino-library) ·
[board definitions](https://github.com/SolderedElectronics/Inkplate-Board-Definitions-for-Arduino-IDE) ·
[free GPIO](https://docs.soldered.com/inkplate/5v2/hardware/free-gpio/) ·
[deep sleep](https://docs.soldered.com/inkplate/5v2/low-power/deep-sleep/) ·
[RTC alarm](https://docs.soldered.com/inkplate/5v2/rtc/alarm/)

### Core

| | |
|---|---|
| Panel | E Ink ED052TC4, 5.17", **1280 × 720**, **3-bit grey (8 levels)**. Full refresh 0.99 s, partial 0.22 s. |
| MCU | ESP32-WROVER-E. **8 MB PSRAM** *(derived)*: the board reports 4.0 MB, the most an ESP32 maps at a time, and a WROVER-E carries either 8 MB or 2 MB. Flash **at least 4 MB** *(unverified)*: the variant sets 4, 8 or 16 MB, the shield prints no suffix, and `partitions.csv` uses 4 MB. Library allocates ~921 kB PSRAM for framebuffers. |
| Radio | Wi-Fi, BT 4.0 BLE |
| USB | USB-C, CH340C UART, 500 mA fuse on VBUS *(schematic)* |
| Battery | 2-pin JST-PH 2.0 mm, 3.7 V Li-ion, MCP73831 charger at ~400 mA *(schematic, R32 = 2.49 k)* |
| RTC | PCF85063A, CR2032 backup holder |
| Storage | microSD (SPI on IO12–15, switched rail) |
| PMIC | TPS65186 (panel rails), TPS7A2633 3.3 V LDO |
| IO expander | PCAL6416A |
| No | touchscreen, frontlight, 5 V boost converter |

Gen2 vs Gen1: 960×540 → 1280×720 panel, I²S DMA panel driver, same 130.6 × 75.2 mm board.

### I²C and easyC

- SDA **GPIO21**, SCL **GPIO22** *(schematic)*. `Inkplate::begin()` calls `Wire.begin()` at the default 100 kHz.
- One easyC connector, K3. Pads 1 = SCL, 2 = SDA, 3 = 3V3, 4 = GND *(schematic)*. The same four signals are on the bottom header.
- Soldered states easyC is pin-compatible with Qwiic and STEMMA QT: black GND, red 3V3, blue SDA, yellow SCL.
- Host pull-ups: R1/R4 **10 kΩ** to 3V3 on SCL/SDA. No jumper to remove them *(schematic)*.
- easyC 3V3 is the main 3V3 net straight from the LDO. No current limit is stated.

### Onboard I²C addresses

| Device | Addr |
|---|---|
| PCAL6416A IO expander (ADDR = GND) | 0x20 |
| TPS65186 PMIC | 0x48 |
| PCF85063A RTC | 0x51 |

No conflict with 0x12, 0x62, 0x70, 0x76/0x77.

### Power

- Inputs: USB-C 5 V or battery, both at once allowed; USB takes over via a P-MOSFET when present *(schematic)*.
- **No 5 V boost.** The VIN pad is ≈5 V only with USB plugged in (VUSB through a Schottky), otherwise VBAT *(schematic)*.
- 3V3: TPS7A2633, **500 mA**, 2 µA quiescent, from VIN. Feeds ESP32, expander, RTC, panel PMIC 3.3 V input, microSD, and the easyC connector.
- Deep sleep 18 µA *(product page)*; 20–30 µA with peripherals asleep *(docs)*. Awake, Wi-Fi and refresh currents: not published.
- `readBattery()`: expander P1_1 enables a MOSFET, 100k/100k divider, `analogReadMilliVolts(35) × 2`.

### Deep sleep and wake

- RTC INT → JP2 (default INT) → **GPIO39** with 10 k pull-up *(schematic)*. Library example: `setAlarmEpoch(..., RTC_ALARM_MATCH_DHHMMSS); esp_sleep_enable_ext0_wakeup(GPIO_NUM_39, 0);` — the example carries the comment "GPIO39 is NOT guaranteed for Inkplate 5v2". Matches what `EpdBoardInkplate::enableWakeOnRtcAlarm()` does. **It works on this board** *(measured)*: the validation build sets a 10 s alarm and every wake logs `ESP_SLEEP_WAKEUP_EXT0` on time. Soldered's warning stands for the family, not for this unit.
- Wake button SW3 → GPIO36, active low. Expander INT → GPIO34.
- **easyC 3V3 stays on in deep sleep.** It is the unswitched LDO output the ESP32 itself runs from. Only microSD and RTC rails are switched. Cutting sensor power needs an external load switch on a free expander pin.
- Free GPIO: expander P1_3–P1_7 on the bottom header; `gpioInit()` sets them OUTPUT LOW. Use `display.expander1.pinMode/digitalWrite(IO_PIN_B3..B7, ...)`. Do not use P0_x.

### Arduino / PlatformIO

- Board define **`ARDUINO_INKPLATE5V2`** (Arduino core `INKPLATE5V2`). Selects `Inkplate5V2Driver.h`, `MULTIPLE_DISPLAY_MODES`, `USES_I2S`.
- No PlatformIO board JSON exists. Community config: `board = esp32dev`, `build_flags = -DARDUINO_INKPLATE5V2 -DBOARD_HAS_PSRAM -mfix-esp32-psram-cache-issue`, `board_build.f_cpu = 240000000L` — the same shape as weather-cal's `platformio.ini`.
- `INKPLATE_1BIT 0`, `INKPLATE_3BIT 1`; `E_INK_WIDTH 1280`, `E_INK_HEIGHT 720`.
- RTC API as used by the kit: `setEpoch`, `getEpoch`, `getRtcData`, `setAlarmEpoch(epoch, match)`, `clearAlarmFlag`. Match modes `_SS`, `_MMSS`, `_HHMMSS`, `_DHHMMSS`, `_WHHMMSS`.
- Do a full update after a run of partial updates *(docs FAQ)*; `setFullUpdateThreshold(n)`.

### Physical *(KiCad PCB, component side, origin top-left, mm)*

- Outline **130.59 × 75.23**, 2.5 mm corner radius, 1.6 mm PCB.
- Mounting: 4 × SMT M3 standoffs at (3.40, 3.40), (127.19, 3.40), (3.40, 71.83), (127.19, 71.83) — pitch **123.79 × 68.43**.
- USB-C (3.00, 60.23) left edge · power button (2.00, 49.23) left · wake button (128.59, 49.23) right · battery JST (28.00, 15.23) · microSD (10.00, 31.23) · **easyC (100.00, 41.23)** · CR2032 (114.00, 41.23) · ESP32 (80.83, 15.80) · panel FPC (27.50, 46.43).
- Header: 1×1 pads on 2.54 mm along the bottom edge (y = 73.73), x = 19.57–111.01: panel group, ESP32 group (GND, 3V3, TXD, RXD, IO12–15, IO34, V_BAT, IO36, IO39), I²C group (GND, 3V3, SDA, SCL), expander group (GND, 3V3, P1_1–P1_7). The pads are 0.8 mm drills, so a header needs round machined pins.
- Panel 124.59 × 69.14 mm centred on the far side; active area 114.56 × 64.44 mm.
- Soldered enclosure: 145.24 × 84.23 × 13.5 mm, sold assembled (€19.95) and published as STL/STEP.

---

## 2. SCD41 — CO₂

Sources: [SCD4x datasheet v1.7](https://sensirion.com/media/documents/48C4B7FB/67FE0194/CD_DS_SCD4x_Datasheet_D1.pdf) ·
[low-power app note](https://sensirion.com/media/documents/077BC86F/62BF01B9/CD_AN_SCD4x_Low_Power_Operation_D1.pdf) ·
[design-in guide](https://sensirion.com/media/documents/0D0C9129/623B1183/Sensirion_CO2_Sensors_SCD4x_design-in_guide.pdf) ·
[Adafruit 5190](https://www.adafruit.com/product/5190) · [learn guide](https://learn.adafruit.com/adafruit-scd-40-and-scd-41) ·
[Sensirion library](https://github.com/Sensirion/arduino-i2c-scd4x) ·
[module STEP](https://sensirion.com/media/documents/260AFF2D/616531AE/Sensirion_CO2_Sensors_SCD4x_STEP_file.step)

### Measures

| | Range | Accuracy | τ63 |
|---|---|---|---|
| CO₂ | 400–5000 ppm (output 0–40 000) | ±(50 ppm + 2.5 %) to 1000; ±(50 + 3 %) to 2000; ±(40 + 5 %) to 5000 | 60 s |
| RH | 0–100 % | ±6 % (15–35 °C) | 90 s |
| T | −10–60 °C | ±0.8 °C (15–35 °C) | 120 s |

Repeatability ±10 ppm. Drift ±(5 ppm + 0.5 %)/year. RH/T specs hold only with the temperature offset set for the enclosure.

### Electrical

- VDD 2.4–5.5 V. **Peak 175 mA typ / 205 mA max at 3.3 V** (115/137 at 5 V), "sustained" during the measurement pulse. Supply ripple must be < 30 mV p-p unloaded; **Sensirion recommends a separate LDO.**
- Average: 15 mA (periodic 5 s), 3.2 mA (low-power periodic 30 s), 0.45 mA (single-shot every 5 min). Idle < 200 µA. Single shot costs 77 mC at 3.3 V.
- I²C 0x62, not changeable. 0–400 kHz. Power-up to idle 30 ms.

### Commands we will use

All words 16-bit MSB-first; each data word followed by CRC-8 (poly 0x31, init 0xFF, no reflect, no final XOR; CRC(0xBEEF) = 0x92).

| Command | Code | Wait | Notes |
|---|---|---|---|
| start_periodic_measurement | 0x21B1 | — | 5 s interval. Only read/data-ready/stop/pressure allowed while running. |
| start_low_power_periodic_measurement | 0x21AC | — | 30 s interval. |
| stop_periodic_measurement | 0x3F86 | 500 ms | |
| measure_single_shot | 0x219D | 5000 ms | Fastest interval 5 s. Datasheet v1.6 dropped the "discard first shot after power-up" note; the 2022 app note still says discard it. |
| read_measurement | 0xEC05 | 1 ms | 9 bytes: CO₂, T, RH words + CRCs. **NACKs if no data** — poll data-ready first. |
| get_data_ready_status | 0xE4B8 | 1 ms | low 11 bits == 0 → not ready |
| set_temperature_offset | 0x241D | 1 ms | word = °C × 65535/175. Default 4 °C. Idle only. |
| set_ambient_pressure | 0xE000 | 1 ms | word = Pa/100, 70 000–120 000 Pa. **Allowed during periodic measurement. Feed the BME688's pressure in.** |
| set_automatic_self_calibration_enabled | 0x2416 | 1 ms | default on |
| perform_forced_recalibration | 0x362F | 400 ms | run ≥ 3 min first, stop, wait 500 ms |
| persist_settings | 0x3615 | 800 ms | EEPROM, ≥ 2000 cycles |
| power_down / wake_up | 0x36E0 / 0x36F6 | 1 / 30 ms | wake_up is never ACKed; verify with get_serial_number |
| get_serial_number | 0x3682 | 1 ms | 48-bit |
| perform_self_test | 0x3639 | 10 000 ms | word 0 → OK |

T = −45 + 175 × word/65535; RH = 100 × word/65535.

### Operating mode for this device (mains)

Run **periodic measurement (5 s)**, or low-power periodic (30 s) if 15 mA average matters. ASC works in both and needs ≥ 3 min of ~400 ppm fresh air weekly. Set `set_ambient_pressure` from the BME688 each cycle. Determine the temperature offset in the finished enclosure after 15 min of thermal equilibrium: `offset_new = T_scd − T_shtc3 + offset_prev`. ASC is **not** available in power-cycled single-shot mode.

### Gotchas

- Self-heating: the default 4 °C offset is a guess; measure it in situ. Design-in guide sanity check: > 0.5 °C from the reference after 15 min, or > 20 ppm between consecutive readings, means the design-in is poor.
- Placement: large opening near the sensor, small dead volume, away from CPU, display, Wi-Fi, regulators, battery; lowest part of the device; out of sunlight and vibration.
- Do not touch or wet the white membrane.
- Settings are RAM-only until `persist_settings`.

### Library

`Sensirion I2C SCD4x` (class `SensirionI2cScd4x`, `begin(Wire, 0x62)`): `startPeriodicMeasurement()`, `getDataReadyStatus()`, `readMeasurement(co2, T, RH)`, `setAmbientPressure(Pa)`, `setTemperatureOffset()`, `persistSettings()`.

### Adafruit 5190 board

- 25.4 × 22.86 mm. Four 3.0 mm holes at (2.54, 2.54), (22.86, 2.54), (2.54, 20.32), (22.86, 20.32) — pitch 20.32 × 17.78.
- Two STEMMA QT connectors, one per side edge, plus a 5-pin header (VIN, 3Vo, GND, SCL, SDA).
- VIN 3–5 V; AP2112K regulator; BSS138 level shifter; **10 kΩ pull-ups on SDA/SCL, no jumper to disable**. Sensor is powered straight from VIN by default ("Sensor Power" jumper). Rev A silkscreen for the two back jumpers is reversed.

---

## 3. PMSA003I — particulates

Sources: [Plantower PMSA003I manual V2.6](https://cdn-shop.adafruit.com/product-files/4632/4505_PMSA003I_series_data_manual_English_V2.6.pdf) ·
[Adafruit 4632](https://www.adafruit.com/product/4632) · [learn guide](https://learn.adafruit.com/pmsa003i) ·
[schematic](https://cdn-learn.adafruit.com/assets/assets/000/092/990/original/sensors_PMSA300I_sch.png) ·
[Eagle files](https://github.com/adafruit/Adafruit-PMSA003I-PCB) ·
[Adafruit_PM25AQI](https://github.com/adafruit/Adafruit_PM25AQI) ·
[AP3602A charge pump](https://cdn-shop.adafruit.com/product-files/3661/AP3602A_B.pdf)

### Measures

- PM1.0 / PM2.5 / PM10 in µg/m³, two flavours: "CF=1, standard particle" (factory) and "atmospheric environment". Use the **atmospheric** ("env") values for indoor readings; the library's AQI uses them.
- Particle counts per 0.1 L for > 0.3 / 0.5 / 1.0 / 2.5 / 5.0 / 10 µm.
- Range 0–500 µg/m³ effective, ≥ 1000 max. Resolution 1 µg/m³. Consistency ±10 % (100–500) / ±10 µg/m³ (0–100). Counting efficiency 50 % @ 0.3 µm, 98 % @ ≥ 0.5 µm.
- Internal update every 2.3 s (stable) to 200–800 ms (fast). Total response ≤ 10 s.

### Electrical — the 5 V question

- Module: **DC 5.0 V (4.5–5.5)**, "needed because the FAN should be driven by 5V". Data pins are 3.3 V logic (L < 0.8 V, H > 2.7 V). Active ≤ 100 mA, standby ≤ 200 µA.
- Adafruit board: **makes its own 5 V** with an AP3602A charge pump from VIN 3–5 V, so it runs from a 3.3 V Qwiic chain. AP3602A: 100 mA continuous, 250 mA for 100 ms, input current ≈ 2 × output → **~200 mA from 3.3 V while the fan runs** *(derived)*.
- Board also has an AP2112K 3.3 V LDO (pull-ups, LED, level shifter) and a BSS138 level shifter. **10 kΩ pull-ups on both sides of the shifter; the connector side is pulled to VIN.** ⇒ a 5 V VIN pulls the shared bus to 5 V, past the SCD41's VDD + 0.3 V absolute maximum. **Keep VIN at 3.3 V**, though the module itself wants 5 V: the charge pump makes that.
- I²C **0x12**, fixed. 100 kHz-class timing. No UART on this variant (pins 6 and 8 NC).

### Interface

One plain 32-byte I²C read, big-endian words:

| Bytes | Field |
|---|---|
| 0–1 | 0x42 0x4D start |
| 2–3 | frame length = 28 |
| 4–9 | PM1.0 / PM2.5 / PM10, CF=1 |
| 10–15 | PM1.0 / PM2.5 / PM10, atmospheric |
| 16–27 | counts > 0.3 / 0.5 / 1.0 / 2.5 / 5.0 / 10 µm per 0.1 L |
| 28 | version |
| 29 | error code |
| 30–31 | checksum = sum of bytes 0–29 |

The sensor updates its registers itself; the host polls. **No I²C commands** for sleep/wake or passive mode. Fan control is the **SET pin** (high = run, low = sleep ≤ 200 µA; on the breakout SET low also shuts the charge pump). RST low resets. Both have 100 k pull-ups on the breakout; drive from a GPIO.

### Warm-up

- **≥ 30 s after wake** for stable data (fan spin-up). Library waits 3 s after power before `begin_I2C()`.
- Intermittent use reported to read high; 2–3 min to settle *(unverified, PMSA003 UART sibling)*.
- Endurance test: SET toggled at 0.5 Hz for 72 h — frequent duty-cycling is within spec.

### Operating mode for this device (mains)

Run the fan continuously (datasheet "active mode", MTTF ≥ 3 years) and poll every few seconds, keeping checksum-valid frames and averaging. SET is optional: the breakout's 100 k pull-up holds it high, so with no wire the fan runs from power-on. Wired to expander P1_3 (§8), it lets the firmware stop and start the fan; stopping it between readings saves dust, at a cost in accuracy per the field reports.

### Gotchas

- Metal shell is GND. Inlet/outlet against the enclosure wall, or a baffle between them; enclosure vent ≥ inlet size; ≥ 20 cm above the floor; not in an air purifier's flow; indoor only; kitchen/bathroom mist needs protection.
- Overreads above ~80 % RH *(studies, unverified)*.
- Module screw holes Ø1.7 mm, thread depth max 3.4 / 1.9 mm.

### Library

`Adafruit_PM25AQI`: `begin_I2C(&Wire)`; `read(&data)` does the 32-byte read and checksum, returns false on a bad frame — retry. Fields `pm25_env`, `pm100_env`, `particles_03um` … plus US/China AQI.

### Adafruit 4632 board

- **35.56 × 50.80 mm**, 13.6 mm tall with the module, 28 g.
- Holes 2.5 mm at (2.54, 2.54), (33.02, 2.54), (2.754, 48.3), (32.754, 15.3).
- Two STEMMA QT connectors on the left/right edges near the bottom (y = 8.89). 7-pin header along the bottom: VIN, 3Vo, GND, SCL, SDA, RST, SET.
- Module 38 × 35 × 12 mm sits on top; fan face away from the PCB; inlet slots on the 12 mm side faces.

---

## 4. BME688 — VOC / gas, pressure

Sources: [Bosch datasheet rev 1.3](https://www.bosch-sensortec.com/media/boschsensortec/downloads/datasheets/bst-bme688-ds000.pdf) ·
[BSEC software](https://www.bosch-sensortec.com/software-tools/software/bme688-and-bme690-software/) ·
[BSEC2 Arduino](https://github.com/boschsensortec/Bosch-BSEC2-Library) ·
[BME68x API](https://github.com/boschsensortec/BME68x_SensorAPI) ·
[Soldered 333203](https://soldered.com/products/bme688-environmental-sensor) · [docs](https://docs.soldered.com/bme688/hardware/) ·
[Soldered library](https://github.com/SolderedElectronics/Soldered-BME688-Sensor-Arduino-Library)

### Measures

- **Gas resistance (Ω)** from a heated metal-oxide layer: lower = more reducing VOCs. Also moved by humidity. Sums VOCs; blind to CO₂.
- With **BSEC** (closed-source Bosch binary): IAQ 0–500 (auto-trimmed to recent history; ~50 good, ~200 polluted), **static IAQ** (recommended for a stationary device), CO₂-equivalent, breath-VOC-equivalent, accuracy 0–3.
- Pressure 300–1100 hPa, ±0.6 hPa absolute, ±0.12 relative. Humidity ±3 % (20–80 %). Temperature ±0.5 °C **"typically above ambient"** — self-heating, see below.
- BME688 over BME680: gas-scanner mode (10-step heater profile, AI-Studio classification). Not needed here.

### Electrical

- VDD 1.71–3.6 V, optimised for 1.8 V (the Soldered board runs it at 3.3 V; heat scales with supply).
- Sleep 0.15 µA. Forced T/P/H ~3.7 µA at 1 Hz. **Heater 12 mA typ, 17 mA peak.** BSEC averages: ULP 0.09 mA, LP 0.9 mA.
- I²C **0x76** (SDO low) default on Soldered; JP1 → 0x77. Up to 3.4 MHz.
- Soldered board: onboard regulator, VCC 3.3–5 V; JP3 regulator enable (NC); JP2 (NO) is not a bypass: Soldered's docs say "when connected, the voltage regulator is powered by 5V". What JP2 joins is unverified, because no schematic is published; check it with a meter before bridging it. **JP5 (NC) 3.3 V pull-ups, JP4 (NC) 5 V pull-ups — cut to disable.** 10 k, from the `103` marking on the board.

### Interface (forced mode, the sequence we need)

Chip ID 0xD0 = 0x61; variant 0xF0 = 0x01. Set osrs_h (0x72), then osrs_t/osrs_p (0x74), gas_wait_0 (0x64, e.g. 100 ms), res_heat_0 (0x5A, computed from calibration), run_gas (0x71 bit 5), then mode = forced (0x74 bits 1:0). Poll new_data (0x1D bit 7). Read P 0x1F–21, T 0x22–24, H 0x25–26, gas 0x2C–2D with **gas_valid (bit 5) and heat_stab (bit 4)** — both must be set. Heater reaches target in 20–30 ms; typical indoor profile **300–320 °C for 100–150 ms**. Rely on the Bosch API for compensation maths.

### BSEC on ESP32

- Runs on ESP32 Arduino (`boschsensortec/bsec2` on PlatformIO, precompiled `libalgobsec`). ROM ~37 kB, RAM ~4 kB. Clickthrough licence.
- Sample rates: **LP 3 s** (0.9 mA) or **ULP 300 s** (0.09 mA). Calibration: accuracy 0 for ~5 min (LP) / ~20 min (ULP), then hours to reach 3; needs both clean and polluted air exposure.
- **State blob 238 bytes** must be saved and restored or calibration restarts. Config blob (~1.9 kB, pick the 3.3 V / 3 s or 300 s / 4 d or 28 d variant) is re-applied each boot. BSEC needs a monotonic clock (`Bsec2::begin` takes a millis function).
- Mains-powered and always awake, LP mode with the state kept in RAM and checkpointed to NVS every few hours is the well-trodden path. Deep-sleep BSEC setups are where the forum failures live.
- The firmware links BSEC2 1.10.2610's `libalgobsec` without Bosch's Arduino wrapper, whose sources need a second copy of the BME68x API; `scripts/bsec.py` adds the headers, the config blobs and the binary. It uses `bme688_sel_33v_3s_4d`, subscribes to the IAQ outputs and to raw pressure at the LP rate, and runs in a FreeRTOS task of its own. Without an output that needs pressure, BSEC asks for no pressure conversion, the BME688 skips it, and the reading comes out near 659 hPa. The Arduino package has no BME688 configuration named for IAQ, but `sel` gives an index from the first sample and reached accuracy 1 in about 4 minutes and 3 in about 40 *(bench)*. Restarted from the state in NVS, it is back at accuracy 3 within 3 minutes *(bench)*.
- BSEC's header gives its pressure input in Pa, but Bosch's own BSEC2 wrapper passes hPa, and so does the firmware. BSEC took 1019 hPa without an error and kept giving an index *(bench)*.

### Self-heating

Die runs above ambient; heater 200–400 °C after the T/P/H read. Bosch offsets 1.33 °C (LP) / 0.47 °C (ULP); users report 1–3 °C. **Use the SHTC3 for T/RH; treat BME688 T/RH as BSEC-internal.**

### Library

Bosch `BME68x Sensor library` (`setTPH(2x,16x,1x)`, `setHeaterProf(300,100)`, `setOpMode(FORCED)`, `fetchData`, `getData`) plus `Bosch-BSEC2-Library` for IAQ. Soldered's library is a thin GPL wrapper of the Bosch one, `begin(0x76)`, no BSEC. Adafruit_BME680 also drives it (default 0x77 — pass 0x76).

### Soldered 333203 board

- **38.0 × 22.0 mm** *(measured)*, four M3 (3.2 mm) corner holes, 1.5 mm header holes. Two easyC connectors, one per short edge; 4-pin header GND/VCC/SDA/SCL on the long edge. Sensor near centre.
- No public hardware repo: Soldered's docs call it "not available yet" and send the files on request.

---

## 5. SHTC3 — temperature and humidity

Sources: [SHTC3 datasheet v4](https://sensirion.com/media/documents/643F9C8E/63A5A436/Datasheet_SHTC3.pdf) ·
[low-power app note](https://sensirion.com/media/documents/00887EF5/6164030A/Sensirion_AppNotes_Humidity_Sensors_SHTC3_Low_Power_Measurement_Mode.pdf) ·
[SHTxx design guide](https://media.digikey.com/pdf/Data%20Sheets/Sensirion%20PDFs/HT_AN_SHTxx_STSxx_Design%20Guide_V1.1_D1.pdf) ·
[Soldered 333032](https://soldered.com/products/temperature-and-humidity-sensor-shtc3-breakout) · [docs](https://docs.soldered.com/shtc3/hardware/) ·
[Adafruit_SHTC3](https://github.com/adafruit/Adafruit_SHTC3) · [Soldered library](https://github.com/SolderedElectronics/Soldered-SHTC3-Temperature-Humidity-Sensor-Arduino-Library)

### Measures (normal mode)

| | Range | Typ accuracy | Max | τ63 | Drift |
|---|---|---|---|---|---|
| RH | 0–100 % | ±2 % (20–80 %, 25 °C) | ±3.5 % | 8 s | < 0.25 %/yr |
| T | −40–125 °C | **±0.2 °C** (5–60 °C) | ±0.4 °C | 5–30 s | < 0.02 °C/yr |

Recommended operating range 5–60 °C, 20–80 % RH; long exposure > 80 % gives a temporary offset that self-recovers.

### Electrical

- VDD 1.62–3.6 V. Sleep **0.3 µA**, idle 45 µA, measuring 430 µA (normal) / 270 µA (low-power). 15.4 µJ per normal reading.
- I²C **0x70, fixed**. Up to 1 MHz. Clock stretching supported; prefer the no-stretch commands on ESP32.
- Soldered board: regulator, VCC 3.3–5 V; **JP2 (NC) 3.3 V pull-ups, JP1 (NC) 5 V pull-ups — cut to disable.** 10 kΩ, from the `103` marking on the board. Level shifter between the header and the easyC side. JP3 (NC) feeds the regulator and JP4 (NO) bypasses it; Soldered's docs say "Ensure JP3 is disconnected if JP4 is connected". The component side carries JP1–JP4 and no JP5.

### Commands

| | Code |
|---|---|
| Wakeup | 0x3517 |
| Sleep | 0xB098 |
| Soft reset | 0x805D |
| Read ID | 0xEFC8 (ID & 0x083F == 0x0807) |
| **Normal, no stretch, T first** | **0x7866** |
| Normal, stretch, T first | 0x7CA2 |
| Low-power, no stretch, T first | 0x609C |

Sequence from sleep: wakeup → ≥ 240 µs → measure → ≥ 12.1 ms (0.8 ms low-power) → read 6 bytes (T MSB, LSB, CRC, RH MSB, LSB, CRC) → sleep. ~13 ms total. CRC-8 poly 0x31 init 0xFF. T = −45 + 175 × S/2¹⁶; RH = 100 × S/2¹⁶. First reading after wakeup is valid.

**Trap:** the Soldered library's `sample()` defaults to **low-power mode** (±0.8 °C). Use `sample(SHTC3_READ)` or Adafruit_SHTC3, which defaults to normal mode and sleeps the part after each read.

### Placement (Sensirion design guide)

"External heat sources close to the sensor will cause increased temperature (and thus decreased RH) readings" — 1 °C error ≈ 5 % RH at 90 %. Conduction from "power electronics, microprocessors, displays" is the most common cause. Put it at the enclosure edge or corner, with airflow across it, isolated from the board by slits, shielded from heated air, out of sunlight. The Soldered board already has the sensor on a slotted thermal island. No polyamide near it; at most one membrane per aperture.

### Soldered 333032 board

- **38.0 × 22.0 mm** *(measured)*, 2 mm corner radius, four Ø3.2 mm (M3) holes inset 3.05 mm on a 32 × 16 mm pitch. Soldered's product page and docs give 22 × 22 mm with two holes, which does not match the board. Two easyC connectors on the short ends; unpopulated 4-pin header on one long edge.
- No public hardware repo: Soldered's docs call it "not available yet" and send the files on request.

---

## 6. The I²C bus

Sources: [NXP UM10204](https://www.nxp.com/docs/en/user-guide/UM10204.pdf) ·
[SparkFun Qwiic](https://www.sparkfun.com/qwiic) · [Adafruit STEMMA QT](https://learn.adafruit.com/introducing-adafruit-stemma-qt/technical-specs) ·
[Soldered Qwiic/easyC](https://docs.soldered.com/qwiic/) · [JST SH](https://www.jst-mfg.com/product/detail_e.php?series=231)

### Connectors

easyC, Qwiic and STEMMA QT are all **JST SH 1.0 mm 4-pin, same order: black GND, red 3V3, blue SDA, yellow SCL**. A stock cable chains a Soldered board to an Adafruit board. Every sensor board here has two connectors in parallel (pass-through); the Inkplate has one. Cable 28 AWG; SparkFun's conservative cable limit **226 mA**, JST contact rating 1 A. The 226 mA is a bundled, long-run derating for 28 AWG — a single short conductor in free air is good to ~1 A, which is also the contact limit. §8's cable 1 carries the whole chain's ground return, up to ~470 mA at peak, on that basis; it is the most heavily loaded Qwiic conductor in the build and the reason the second return (step 9) exists. STEMMA (non-QT, JST PH 2 mm) is a different thing.

### Addresses

0x12 PMSA003I · 0x62 SCD41 · 0x70 SHTC3 · 0x76 BME688 · plus 0x20 / 0x48 / 0x51 on the Inkplate. **No conflicts.**

### Pull-ups

| Where | Value | Removable? |
|---|---|---|
| Inkplate host | 10 k | no |
| Adafruit SCD41 | 10 k | no jumper |
| Adafruit PMSA003I | 10 k (connector side) | no jumper |
| Soldered BME688 | 10 k *(marked 103)* | JP5 |
| Soldered SHTC3 | 10 k *(marked 103)* | JP2 |

Parallel total **2.0 kΩ** per line; sink 1.65 mA at 3.3 V. Spec minimum 967 Ω (3 mA sink) — **within spec**. At 100 kHz (Inkplate default) the rise-time budget is comfortable. At 400 kHz, 2.0 kΩ allows only ~177 pF of bus, marginal with four cables. Recommendation: **stay at 100 kHz and cut nothing.** Cutting JP5 (BME688) and JP2 (SHTC3) would give 3.3 kΩ, which buys headroom only at 400 kHz.

### Length

400 pF bus limit; ~40–100 pF per metre of cable *(unverified)* plus ~10 pF per device pin. Four cables of 50–200 mm keep the chain under 0.8 m — fine.

---

## 7. Power

### Budget on the 3.3 V rail

| Load | Typical | Peak |
|---|---|---|
| PMSA003I via its charge pump, fan running | ~200 mA *(derived)* | 250 mA / 100 ms |
| SCD41, periodic 5 s | 15 mA | **175–205 mA** during each measurement |
| BME688, BSEC LP | 0.9 mA | 17 mA |
| SHTC3 | 0.4 mA | 0.9 mA |
| **Sensors total** | **~215 mA** | **~470 mA** |
| ESP32-WROVER-E awake, Wi-Fi | ~80–150 mA *(typical figure, not published by Soldered)* | 300+ mA TX bursts |
| Panel refresh via TPS65186 | not published | not published |

The Inkplate's TPS7A2633 is **500 mA** and must also carry the ESP32 and panel PMIC. Sensor peaks plus a Wi-Fi burst exceed it. Sensirion separately demands < 30 mV ripple and recommends its own LDO for the SCD41. SparkFun's guidance for high-current Qwiic chains is to inject power from a separate supply and cut the 3V3 wire.

### The fix

A **3.3 V LDO module rated ≥ 600 mA** fed from the Inkplate's **VIN pad** (≈5 V on USB), output into the sensor chain. The build uses an AMS1117-3.3 module: 800 mA maximum and about 1.1 V of dropout, which the VIN pad's ~4.7 V on USB covers, and a power LED that draws a little on its own. The Inkplate's own regulator then powers only the Inkplate. The USB VBUS fuse is 500 mA total, so the whole device must stay under that: Inkplate (~150 mA typical) + sensors (~215 mA) fits; peaks are brief.

---

## 8. Wiring

### Circuit

```
 USB-C 5 V
    │
    ▼
 Inkplate 5 Gen2
    │
    ├─ VIN pad ─────────────────────► AMS1117-3.3  IN
    ├─ expander-group GND ──────────► AMS1117-3.3  GND       regulator's reference only, a few mA
    │                                 AMS1117-3.3  OUT ─────► PMSA003I header VIN    3.3 V for the whole chain
    │
    ├─ expander P1_3 ───────────────────────────────────────► PMSA003I header SET    fan control, optional
    │
    ├─ easyC K3 ── cable 1: GND · SDA · SCL, 3V3 cut ───────► PMSA003I header GND · SDA · SCL   bus in, chain's ground return out
    │
    └─ ESP32-group GND ── step 9 ───────────────────────────► SCD41 header GND        second ground return, from the sensitive board

   ┌─ PMSA003I  (Adafruit 4632)   0x12   heaviest load first: power enters at its header, ground leaves by cable 1
   │     cable 2: stock, from socket B
   │     ▼
   ├─ SCD41     (Adafruit 5190)   0x62   second heaviest; gets BME688 pressure each cycle; carries step 9's return
   │     cable 3: stock
   │     ▼
   ├─ BME688    (Soldered)        0x76   JP1 moves it to 0x77 if 0x76 is ever taken
   │     cable 4: stock
   │     ▼
   └─ SHTC3     (Soldered)        0x70   LAST — at the enclosure edge, upstream of the fan,
                                         away from the heater and the Inkplate. Second socket unused.
```

### What connects to what

| # | From | To | Wire |
|---|---|---|---|
| 1 | Inkplate **VIN pad** | AMS1117 **IN** | 28 AWG jumper, Dupont at the AMS1117 end |
| 2 | Inkplate **expander-group GND** | AMS1117 **GND** | 28 AWG jumper, Dupont both ends |
| 3 | AMS1117 **OUT** | PMSA003I header **VIN** | 28 AWG jumper, Dupont both ends |
| 4 | Inkplate **expander P1_3** | PMSA003I header **SET** | 28 AWG jumper, Dupont both ends — optional, see below |
| 5 | Inkplate **easyC K3** | PMSA003I header **GND, SDA, SCL** | cable 1: a Qwiic cable with its plug kept at the Inkplate end, the other end cut and re-terminated with three Dupont crimps; **3V3 conductor removed** |
| 6 | PMSA003I **easyC socket B** | SCD41 either socket | cable 2: stock Qwiic |
| 7 | SCD41 other socket | BME688 either socket | cable 3: stock Qwiic |
| 8 | BME688 other socket | SHTC3 either socket | cable 4: stock Qwiic |
| 9 | Inkplate **ESP32-group GND** | SCD41 header **GND** | 28 AWG jumper, Dupont both ends — a second ground return in parallel with cable 1's, see below |

Every sensor board has two easyC sockets wired in parallel, so "either" is
literal. The SHTC3 is last, so one of its sockets stays empty. The PM board's
7-pin header is VIN, 3Vo, GND, SCL, SDA, RST, SET: you use **VIN, GND, SCL,
SDA and SET** and leave 3Vo and RST empty. Cable 1 lands on that header,
not on a socket: socket B carries cable 2, and in the desk enclosure socket A
faces a wall.

In the desk enclosure, every conductor that leaves the Inkplate (rows 1, 2,
4, 5 and 9) also crosses the head-to-base pogo connector. The
[enclosure README](../hardware/enclosure/v1/README.md) has the routing.

**Step 4 is optional.** The PM breakout pulls SET high through 100 kΩ (§3),
so without the wire the fan runs from power-on and every reading is valid.
With it, the firmware controls the fan: the Inkplate library drives P1_3 low
at boot, which stops the fan, and the firmware drives it high when it starts
the sensors, so the 30 s warm-up counts from then. The validation build
reports a missing SET wire as a warning, not a failure.

On the Inkplate, steps 2 and 4 use the expander group's GND and P1_3 pads,
and step 9 the ESP32 group's GND. The Inkplate's four plain GND pads — panel,
ESP32, I²C and expander groups — are the same net and interchangeable;
**AGND** in the panel group is not, leave it alone.

The VIN pad is a 4 × 4 mm surface pad with no hole (PAD3 in Soldered's KiCad
board). The wire unplugs at the AMS1117 end.

**Cable 1** keeps its JST-SH plug at the Inkplate end only. Cut the other
plug off, strip GND, SDA and SCL and crimp a Dupont on each (three single
housings, or one 1×3 if the pins line up — on the PM header they are
GND · SCL · SDA in a row, so they do). The 3V3 conductor is cut back and
insulated, not crimped. On a standard cable that is the **red** wire (black
GND, red 3V3, blue SDA, yellow SCL); on a cable with other colours, find 3V3
by position against the socket's silkscreen or with a meter before cutting.
Leave red in and you parallel the Inkplate's 500 mA regulator with the
AMS1117, which is the fault this whole section exists to avoid.

**Step 9** needs a header on the SCD41 board: five machined round pins
soldered to its VIN · 3Vo · GND · SCL · SDA row, with a single Dupont housing
on GND and the other four empty.

### Ground: one wire per crimp

Ground has four endpoints on this device — the Inkplate's ground plane, the
AMS1117's single GND pin, the PM header and the SCD41 header — and a Dupont
housing takes one crimp, so any scheme that chains them (Inkplate → AMS1117 →
PM) puts two wires on the regulator's GND pin. Instead each endpoint gets its
own wire back to the Inkplate's ground plane (**star grounding**), each on its own Inkplate GND pad:

- the AMS1117's GND pin by step 2 (expander-group GND), carrying only the
  regulator's own few mA,
- the PM board, and through it the whole chain, by cable 1's GND conductor
  (easyC K3),
- the SCD41 by step 9 (ESP32-group GND), a second return in parallel with
  cable 1's that starts at the board whose supply matters most.

The chain's return current — up to ~470 mA at peak — therefore flows down
cable 1 straight to the Inkplate, not through the regulator's ground wire. The
regulator's reference stays clean and nothing needs double-crimping. Unplug
the AMS1117 and the bus still has its ground.

### Current in each wire

| Wire | typ / peak | Carrier | Margin |
|---|---|---|---|
| 1 · VIN → AMS IN | 220 / 475 mA | 28 AWG, Dupont | fine — 28 AWG is ~1.4 A in free air, Dupont ≥ 1 A |
| 2 · GND → AMS GND | ~5 mA | 28 AWG | — |
| 3 · AMS OUT → PM VIN | 215 / 470 mA | 28 AWG, Dupont | fine |
| 5 · cable 1 GND (chain return) | 215 / 470 mA, less whatever step 9 takes | 28 AWG, JST-SH 1 A/contact, Dupont | fine |
| 9 · SCD41 GND → Inkplate | share of the SCD41's 15 / 205 mA | 28 AWG, Dupont | — |
| 4, 5 · SET, SDA, SCL | < 1 mA | — | — |
| 6 · PM → SCD41 | 16 / 225 mA | 28 AWG, JST-SH | fine |
| 7, 8 · onward | 1.3 / 18 mA · 0.4 / 0.9 mA | — | — |
| 1, 2, 4, 5, 9 · pogo pins, desk enclosure only | as above; VIN and cable 1 GND are the heaviest | one pin each, 1 A *(assumed: the connector is rated 1 A, per pin unstated)* | fine |

Ampacity is not the constraint anywhere; a Dupont jumper only *looks* heavier
than a Qwiic conductor because its insulation is thicker — the copper is the
same 28 AWG.

**Voltage drop is the one thing to watch, and it is mostly contacts.** The
SCD41's own 175 mA measurement pulse goes out AMS OUT → PM header → socket B →
cable 2 → SCD41, and comes back either the same way to cable 1, or straight
down step 9. Over runs of a few centimetres (cable 2 is 45 mm) the copper is
only a few tens of mΩ; the crimp and plug contacts at 10–20 mΩ each are what
add up. Without step 9 the loop crosses
eight of them (~130–210 mΩ, **25–35 mV** at the sensor during its pulse, on
the line of Sensirion's 30 mV ripple guidance in §2). With step 9 the return
half is two Dupont contacts in parallel with the four-contact path back
through the PM board, and the loop falls to roughly 90–140 mΩ, **≈ 15–25 mV**.
In the desk enclosure each return also crosses one pogo contact, whose
resistance the connector's listing does not give; at 30–100 mΩ *(assumed)* the
loop comes to roughly 105–195 mΩ, **≈ 18–34 mV**.
That guidance is a ripple figure, not an operating limit (the part runs from
2.4–5.5 V), so this is margin, not a fault; clean crimps matter more than
cable length. Two returns landing on the same ground plane a few centimetres
apart is not a ground loop.

Chain order is chosen for **cable voltage drop** (heavy loads nearest the
injection point) and **heat** (reference sensor farthest from everything warm).

### Can I just daisy-chain it all off the Inkplate?

**For bench bring-up, yes.** Every board runs at 3.3 V on an ordinary Qwiic
cable, with nothing to change on any of them; the PMSA003I's module needs 5 V
for its fan, but the breakout makes that itself (§3). Plug the chain into
easyC K3 with stock cables throughout, and everything enumerates and reads.

**For the built device, no**, for reasons of current, not of any one board:

- The Inkplate's 3.3 V rail cannot carry the sensor peaks on top of the
  ESP32, the panel PMIC and Wi-Fi bursts (§7).
- ~200 mA for the PM board would flow through every upstream board's
  connectors and three cables' worth of contacts and copper. The drop, not the
  ampacity, is the problem: SparkFun's conservative figure for a Qwiic cable
  is 226 mA, but the contacts are rated 1 A.

Hence the separate regulator and the heaviest-load-first order above. The
symptom if you skip it is an intermittent brown-out when the fan, an SCD41
measurement peak and a Wi-Fi transmit coincide — the hardest kind of fault to
find later. The regulator's 3.3 V goes to the PM board's VIN; the VIN pad's
5 V never does (§3).

---

## 9. The enclosure

The desk enclosure is in [`hardware/enclosure/v1/`](../hardware/enclosure/v1/README.md): where each board
sits and why, the fasteners, the cable routing, the head-to-base pogo connector, and the 3D models it is
built from. The placement rules it follows come from each part's section here: §2 (SCD41), §3 (PMSA003I),
§4 (BME688) and §5 (SHTC3).

---

## 10. Open questions

1. **PMSA003I input current at 3.3 V** is derived from the charge-pump datasheet, not measured. Measure; it sets the LDO rating.
2. **Inkplate awake / Wi-Fi / refresh currents** are unpublished. Measure the whole device on USB to confirm it sits under the 500 mA VBUS fuse.
3. **What the BME688 board's JP2 joins** (§4). Soldered's docs say only that it powers the regulator from 5 V, and no schematic is public. A continuity check across JP2, or the hardware files Soldered sends on request, would settle it.
4. **Pogo contact resistance** in the desk enclosure. The connector's listing gives none, so §8 assumes 30–100 mΩ. Measure across a mated pair with ~200 mA flowing.
5. **Flash size** of the Inkplate's ESP32-WROVER-E: 4, 8 or 16 MB by variant, and the module's shield prints no suffix. `esptool.py flash_id` over USB settles it; it resets the board.

---

## Decision Log

Dated findings and decisions behind the text above, oldest first.

- **2026-09-03**: distilled from the datasheets.
- **2026-09-03**: the first wiring plan chained Inkplate → BME688 → SHTC3 → SCD41 → PMSA003I and fed all four from the Inkplate's 3V3 through the chain. Order, connectors, addresses and pull-ups were fine. Power was not: the Inkplate's 500 mA LDO also carries the ESP32, the SCD41 wants a quiet supply, and the two heavy loads sat at the far end, where the drop is worst. Nor was the SHTC3's place: the reference sat between the BME688's heater and the SCD41. The PM fan's SET pin was unused. §8's circuit replaced the plan.
- **2026-09-09**: the RTC alarm wakes this board on GPIO39, though Soldered does not guarantee it on the 5 Gen2. `pio run -e esp32-validate` sleeps 10 s on the alarm and wakes on `ESP_SLEEP_WAKEUP_EXT0` every cycle; an ESP32 timer armed at 15 s as a backstop has never had to fire.
- **2026-09-09**: the SCD41 board is the Adafruit 5190. Soldered sells no SCD41; their CO₂ board is the SCD43.
- **2026-09-10**: the Soldered BME688 and SHTC3 boards carry `103` resistors beside their pull-up jumpers, so 10 kΩ, and the §6 total of 2.0 kΩ stands.
- **2026-09-12**: on the bench, BSEC with `bme688_sel_33v_3s_4d` reached accuracy 1 in about 4 minutes and 3 in about 40, and took 1019 hPa as its pressure input without an error.
- **2026-09-12**: with calipers, the Soldered SHTC3 and BME688 boards are both 38.0 × 22.0 mm with four Ø3.2 mm holes on a 32 × 16 mm pitch. For the SHTC3 this overrides Soldered's product page and docs, which give 22 × 22 mm and two holes.
- **2026-09-13**: on the bench, BSEC restarted from the state in NVS was back at accuracy 3 within 3 minutes.
- **2026-09-13**: the wiring became one wire per crimp, with ground starred at the Inkplate and cable 1 landing on the PM header. The draft before it chained ground Inkplate → AMS1117 → PM, which put two wires on the regulator's one GND pin.
- **2026-09-14**: Soldered's pages checked again. Neither Soldered sensor board has a public hardware repo, their docs describe the BME688's JP2 only as feeding the regulator from 5 V, and the Inkplate's BOM names its module only as "ESP32-WROVER", so the PSRAM size stays unverified.
- **2026-09-14**: the head-to-base pogo connector is rated 1 A, with no per-pin figure and no contact resistance. §8 takes 1 A per pin and assumes 30–100 mΩ per contact.
- **2026-09-14**: the module is an ESP32-WROVER-E; its shield prints the name but no variant suffix. The board's Diagnostics report shows 4.0 MB of PSRAM, which rules out the 2 MB variants, so it carries 8 MB. The flash stays 4, 8 or 16 MB.
