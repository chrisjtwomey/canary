# Architecture — where the env monitor departs from the kit, and how

How this device differs from the weather calendar that [epd](https://github.com/chrisjtwomey/epd)
came out of, and what it builds on the kit. [HARDWARE.md](HARDWARE.md) has the numbers; the
[Decision Log](#decision-log) has the history.

## 1. What the kit assumes

`epd` was extracted from a weather calendar, and its client model is that
device's: **wake, fetch a PNG, draw it, deep-sleep until the server says.**
The client is dumb and battery-powered. All data lives server-side. The
server decides *when* (`X-Next-Refresh-Seconds`) and *what*
(`X-Next-URL`) from a daily list of wall-clock times.

## 2. What is different here

| | Weather calendar | Env monitor |
|---|---|---|
| Power | LiPo, years | **USB mains** (HARDWARE §7) |
| Data origin | server fetches from APIs | **the client holds the sensors** |
| Cadence | 7 wakes a day | readings every few seconds, display every few minutes |
| Client between refreshes | deep sleep | **awake**: sensors need it (SCD41 periodic mode with ASC, BSEC calibration state, PM fan warm-up) |
| Panel | Inkplate 10, 4 greys used | Inkplate 5 Gen2, **8 greys** |

Three of those change the design. The panel is one config line.

## 3. Three differences in the design

### 3.1 The firmware runs an awake loop, not `run_app()`

`run_app()` is epd's deep-sleep state machine. Keeping the ESP32 awake is not
a tweak to it; it is a different program, and `src/main.cpp` owns it:

```
setup:  board.begin(); wifi; ntp; sensors.begin()
loop:   every 5 s                        sensors.sample()     (SCD41 periodic, BME688 via BSEC, PMSA003I frames, SHTC3)
        every 60 s                       POST /readings       one JSON document, with the board's own status beside it
        when X-Next-Refresh-Seconds ends GET the named page → draw; a failed fetch keeps the old image and backs off
BSEC:   a FreeRTOS task of its own; its state goes to NVS when accuracy first reaches 3 and every six hours after
```

The loop composes epd's WiFi, time, download, `postJson`, image and back-off
helpers, the logger and `IBoard`. The kit stays a library, not a framework:
it does not need to know what a sensor is.

### 3.2 Readings travel client → server by HTTP POST

The board posts one document a minute to `/readings`, in the layout of
[READINGS.md](READINGS.md). epd's `DisplayServer(ingest=...)` hands it to
`ReadingsIngest`, which keeps the newest document for the Diagnostics page
and, with `source.kind: store`, appends it to epd's `ReadingsStore` (SQLite).
`IngestSource` serves the store to the pages as the datasets `latest`,
`history_24h` and `history_72h`, and `SeaLevelSource` reduces the pressure on
the way. With `source.kind: mock`, `MockReadingsSource` serves the simulated
room under the same names. The Diagnostics page reads `status`.

The reading schema is the project's (`co2_ppm`, `pm2_5`, `iaq`, `temp_c`, …);
the kit stores a timestamped JSON document and does not interpret it. BSEC's
learned state rides along in a `calibration` block, which `CalibrationStore`
keeps and `GET /calibration` hands back after the board restarts.

### 3.3 The schedule is an interval, not a list of times

"Every five minutes" as a list of wall-clock times would be 288 entries. epd's
`display` block has `pools` of images and a `schedule` of `type: times` or
`type: interval`. This device uses `interval` with `every: 300`, so refreshes
land on :00, :05, … on the wall clock; the weather calendar keeps `times`.
[CONTRIBUTING.md](../CONTRIBUTING.md) explains the pools.

## 4. What stays as the kit has it

- The wire contract: `GET /<page>.png` with `X-Next-Refresh-Seconds` and `X-Next-URL`. The awake client honours the header by waiting instead of sleeping.
- `DisplayServer`, `Page`, `regenerate()`, `DataSource`, the config loader, the MQTT log relay.
- `IBoard` and `EpdBoardInkplate`. Inkplate 5 Gen2 is `-DARDUINO_INKPLATE5V2`; GPIO39 RTC wake matches the schematic, though this device does not sleep.
- Rendering: `GreyscaleQuantiser` at eight levels for the panel's eight greys, one argument.

## 5. Shape of the repo

```
platformio.ini                 envs: esp32 (the drivers), esp32-mock (-DUSE_MOCK_SENSORS), esp32-validate, native, sim
partitions.csv
src/main.cpp                   the awake loop from §3.1
src/defaults.example.cpp       copy to defaults.cpp: WiFi, server URL, MQTT logging
include/sensors/  src/sensors/
  Readings.h  ReadingsJson.cpp                  what the sensors return, and the wire format in READINGS.md
  IShtc3.h  IScd41.h  IPmsa003i.h  IBme688.h    one interface per part, shaped by its datasheet
  IClock.h  II2cBus.h                           the clock and bus seams
  SensorSuite                                   the four sensors as one begin() and one sample()
  Shtc3Driver  Scd41Driver  Pmsa003iDriver  Bme688Driver  SensirionI2c  Pmsa003iFrame
  IBsec.h  BsecRunner  BsecLibrary              BSEC, in a task of its own
  SensorValidation                              the bench routine's checks
  mock/                                         EnvModel, LaggedValue and the four mocks
include/net/  src/net/         Backlog, Calibration, ClientStatus, RefreshTimer, Url
src/sim/main.cpp               the sensor loop as a host binary
src/validate/main.cpp          the bench routine
lib/bme68x/                    Bosch's BME68x API
scripts/                       bsec.py, version.py
test/                          host tests, native env
server/
  server.py                    config, sources, pages, DisplayServer(...).run()
  sources/                     the mock room, readings ingest, calibration store, device status, sea-level pressure
  pages/                       Breathe, Comfort, Dust, Air, Day, Diagnostics, and the trace and delta pages
  metrics.py                   derived values and wording
  static/                      CSS, fonts, charts.js
  config.example.yaml
hardware/enclosure/v1/         the desk enclosure
docs/
```

## 5.1 The sensor seam

`main.cpp` names a concrete sensor type in exactly one place, a
`#if defined(USE_MOCK_SENSORS)` block that constructs either the mocks or the
real drivers and binds them to `IShtc3&`, `IScd41&`, `IPmsa003i&`, `IBme688&`.
Everything else — including the whole sampling protocol — is written against
those interfaces in `SensorSuite`, so the mocks exercise the code that will
run on the device rather than a parallel copy of it.

`SensorSuite::sample()` runs the datasheet sequence: wake the SHTC3, measure,
wait 13 ms, read, put it back to sleep; one BME688 forced cycle, then feed its
pressure to the SCD41 so the CO₂ conversion is right; take whatever the
SCD41's periodic mode has ready; read a PM frame, retrying once on a bad
checksum, and only after the fan's 30 s warm-up.

The waits are real, so the clock is injected (`IClock`): `ArduinoClock` on the
device, a fake the tests drive. A sample costs ~150 ms of wall clock, nearly
all of it the BME688 heater — 3% of the 5 s cadence, and `::delay()` yields on
ESP32, so WiFi keeps running. If that ever becomes a problem the interfaces
already return false-when-not-ready, so `sample()` can become a state machine
without touching the drivers.

`-DUSE_MOCK_SENSORS` picks the mocks; without it the drivers talk to the
parts. The `esp32` and `esp32-mock` environments are that one flag apart.

The drivers reach the bus through `II2cBus`, for the reason `IClock` exists:
the command sequences, the CRCs and the conversions are what a driver gets
wrong, and a host test cannot drive `Wire`. `ArduinoI2cBus` wraps the `Wire`
instance `Inkplate::begin()` has already started; `test/test_drivers` drives
the same code against parts that answer the bus the way their datasheets
describe.

The BME688 is the exception to writing the registers here. Its compensation
reads twenty calibration coefficients out of the part and the failure mode
is a plausible wrong number, so Bosch's own C API does that arithmetic
(`lib/bme68x`, v4.4.8, BSD-3-Clause). It reaches the bus through function
pointers, so it sits behind `II2cBus` like everything else, and it has no
Arduino dependency, so it builds for the host tests too. IAQ comes from
BSEC, which drives the part through the same driver from a task of its
own; `BsecBme688` hands `SensorSuite` the newest cycle BSEC ran, so the
suite's sequence is the same with BSEC as without it.

## 6. Mocks — what "as close as possible" means

The value is in the **timing and the quirks**, not in emulating registers.
Each mock implements `ISensor` and reproduces what the datasheet says the
real part does:

| Mock | Reproduces |
|---|---|
| `MockScd41` | 5 s measurement interval; `data_ready` false in between; missed intervals dropped, not queued; first shot after power-up discarded; ±10 ppm repeatability noise; commands refused while measuring and for 500 ms after stop; `set_ambient_pressure` changes the answer |
| `MockPmsa003i` | 3 s boot then 30 s fan spin-up with counts ramping from zero; 2.3 s frame cadence with stale bytes in between; occasional checksum failure; SET-low silences it and restarts the warm-up |
| `MockBme688` | forced-mode timing (TPH + heater); `heat_stab` false on the first cycle and whenever the profile is too short or too hot; gas resistance falls with VOC and with humidity; pressure tracks the model |
| `MockShtc3` | 12 ms measurement, 0.8 ms low-power; sleep/wake with NACKs when asleep; ±0.1 °C / ±0.1 % RH repeatability, ±0.4 in low-power mode |

### Warm-up and response time

Every reading trails what it measures, and two of the parts warm themselves.
`LaggedValue` is the shared first-order lag; each mock applies the τ63 its
datasheet quotes:

| | τ63 |
|---|---|
| SHTC3 temperature / humidity | 15 s (quoted 5–30 s, design-dependent) / 8 s |
| SCD41 CO₂ / humidity / temperature | 60 s / 90 s / 120 s |
| BME688 gas / humidity | 92 s (ULP duty cycle) / 8 s |
| PMSA003I concentration | 4 s, from "total response time ≤10 s" |

Self-heating rises from nothing after power-on rather than appearing at
once, with a 300 s time constant — not a datasheet figure, but it puts the
part within 5% at the fifteen minutes Sensirion's design-in guide asks you
to wait before judging the temperature offset.

The visible consequence, and the reason the SHTC3 is the display reference:

```
  time    SHTC3   SCD41   BME688
  14:00    18.4       -    18.4
  14:04    18.3    16.7    19.3
  14:12    18.4    18.3    19.8
  14:20    18.4    18.4    19.9
```

The SCD41 reads about 4 °C **low** at a cold boot, because its default
offset subtracts self-heating the part has not produced yet. The SHTC3 has
no meaningful self-heating (16 µW) and no electrical warm-up at all — 240 µs
to idle, first reading valid — so it is steady from the first sample.

The Python mock source always runs settled, since it replays three hours
before the window it returns. Pages therefore never see the warm-up, which
is what you want while designing them.

`EnvModel` is the room: CO₂ rises with occupancy and decays with ventilation
(τ ≈ 60–90 min), PM has cooking/cleaning spikes, VOC has a baseline and
events, T/RH follow a diurnal curve with the heating on. The same model,
ported to Python, feeds `MockReadingsSource` so the pages are developed
against the same shapes the firmware will send.

---

## Decision Log

Dated decisions and status behind the text above, oldest first.

- **2026-09-03**: proposed: an awake loop, readings posted to the server, and an interval schedule, with the kit additions they need (`postJson`, a `refresh_cycle()` helper, an interval schedule, `ReadingsStore` and `IngestSource`, `POST /readings`). Four questions were open: HTTP or MQTT for the readings; the PM fan always on or duty-cycled; which SCD41 breakout; firmware in `firmware/` or at the repo root.
- **2026-09-03**: the firmware scaffold at the repo root, `EnvModel`, the four mocks and their host tests; the server with `MockReadingsSource`, the first pages and `config.example.yaml`.
- **2026-09-04**: epd's `display` block landed: `pools` of images and a `schedule` of type `times` or `interval`, round-robin over pools and within them, with random starts reshuffled every few hours. `postJson` and `DisplayServer(ingest=...)` landed. `refresh_cycle()` was not needed: the awake loop composes the kit's WiFi, download, draw and back-off helpers directly. The awake loop ran end to end against the mocks, drawing on the server's cadence and posting one readings document a minute with the board's `client` status. Until the store existed, the server kept only the newest document, for the Diagnostics page.
- **2026-09-04**: the build settled three of the four questions. Readings go by HTTP POST: one route in `DisplayServer`, testable with Flask's test client, and an MQTT republish can follow on the server when Home Assistant enters the picture, with no change to the firmware. The firmware sits at the repo root, like the weather calendar's. The PM fan runs all the time.
- **2026-09-09**: the four drivers landed behind `II2cBus`, with host tests. The SCD41 board is the Adafruit 5190 (inventory item 92). The mocks were not corrected against logs of the real parts; that needs a log of each part.
- **2026-09-12**: `ReadingsStore` and `IngestSource` are in epd from 0.5.0, and `source.kind: store` serves them to the pages. BSEC runs for the BME688's IAQ index.
