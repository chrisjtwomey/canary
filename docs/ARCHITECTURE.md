# Architecture — where the env monitor departs from the kit, and how

Status: **proposal, 2026-09-03.** Nothing here is built. It reads
[HARDWARE.md](HARDWARE.md) for the numbers and the extraction plan for what
`epd` provides today.

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
| Cadence | 7 wakes a day | readings every seconds, display every few minutes |
| Client between refreshes | deep sleep | **awake**: sensors need it (SCD41 periodic mode with ASC, BSEC calibration state, PM fan warm-up) |
| Panel | Inkplate 10, 4 greys used | Inkplate 5 Gen2, **8 greys** |

Three of those change the design. The panel is one config line.

## 3. Three decisions

### 3.1 The firmware runs an awake loop, not `run_app()`

`run_app()` is the deep-sleep state machine. Keeping the ESP32 awake is not
a tweak to it; it is a different program:

```
setup:  board.begin(); wifi; ntp; sensors.begin()
loop:   every 5 s     sensors.poll()            (SCD41 periodic, BME688 via BSEC LP, PMSA003I frames, SHTC3)
        every 60 s    POST /readings {json}     to the server
        every 5 min   GET /now.png → draw       (on the server's X-Next-Refresh-Seconds cadence)
        every N hours checkpoint BSEC state to NVS
```

**Kit impact — small.** `EpdClient` already has the pieces this loop needs
as free functions: `configureWiFi`, `configureTime`, `downloadFile`,
`loadImage`, the logger, `IBoard`. It gains:

- `postJson(url, body) -> esp_err_t` in `network_utils` (there is only a GET today).
- A `refresh_cycle()` helper that does GET → draw → return the next-refresh seconds, so both programs share the image path and the header parsing.
- Nothing removed. `run_app()` and the weather calendar are untouched.

The env-monitor's `main.cpp` owns the loop. The kit stays a library, not a
framework: it does not need to know what a sensor is.

### 3.2 Readings travel client → server by HTTP POST

Two candidates: **HTTP POST** to the display server, or **MQTT publish** to a
broker the server subscribes to.

| | HTTP POST `/readings` | MQTT |
|---|---|---|
| Moving parts | none new | a broker (one probably exists: the kit's log relay uses one) |
| Home Assistant | server can republish to MQTT later | native |
| Firmware | `postJson`, 20 lines | PubSubClient is already linked for logging |
| Testing | Flask test client, no infra | needs a broker or a fake |
| Failure mode | server down → readings lost until retry | broker down → same |

**Recommendation: HTTP POST now.** It is one route in `DisplayServer` and
testable with what the kit already has. Add an MQTT republish on the server
side when Home Assistant enters the picture; the firmware never changes.

**Kit impact:**

- `DisplayServer` gains `POST /readings`: validate JSON, hand it to a `ReadingsStore`.
- `epd_server/store.py` — `ReadingsStore`: SQLite, one table, append and range queries. Survives server restarts, which an in-memory ring would not.
- `epd_server/source.py` — `IngestSource(DataSource)` over the store: datasets `latest` and `history(hours=…)`. Pages declare `requires = ("latest", "history_24h")` exactly as the weather pages do.

The reading schema is the project's (`co2_ppm`, `pm25_ugm3`, `iaq`, `temp_c`, …); the kit stores a timestamped JSON document and does not interpret it.

### 3.3 The schedule is an interval, not a list of times

`display_schedule` is `{"08:00:00": today.png, …}`. "Every five minutes"
would be 288 entries. The kit gains an interval schedule:

```yaml
display_schedule:
  every: 300        # seconds; aligned to the wall clock so refreshes land on :00, :05, …
  page: now.png
```

`next_wake` / `next_regen` handle both shapes; `DisplayServer` does not
care which. The weather calendar keeps its list.

## 4. What stays exactly as it is

- The wire contract: `GET /<page>.png` with `X-Next-Refresh-Seconds` and `X-Next-URL`. The awake client honours the header by waiting instead of sleeping.
- `DisplayServer`, `Page`, `regenerate()`, `DataSource`, the config loader, the MQTT log relay.
- `IBoard` and `EpdBoardInkplate`. Inkplate 5 Gen2 is `-DARDUINO_INKPLATE5V2`; GPIO39 RTC wake matches the schematic even though this device will not sleep.
- Rendering: `GreyscaleQuantiser(levels=8)` — the payoff from step 4, one argument.

## 5. Shape of the env-monitor repo

```
firmware/                      PlatformIO project (or src/ at root, like weather-cal)
  platformio.ini               esp32dev + -DARDUINO_INKPLATE5V2, lib_deps symlink://../epd/firmware, boards/inkplate
  src/main.cpp                 the awake loop from §3.1
  src/defaults.cpp             WiFi, server URL, MQTT logging (gitignored, example committed)
  include/sensors/
    Readings.h                 what each sensor returns, and the posted set
    IShtc3.h  IScd41.h  IPmsa003i.h  IBme688.h    one interface per part, shaped by its datasheet
    IClock.h                   millis() / waitMs(); ArduinoClock on the device
    SensorSuite.h              the four sensors as one begin() and one sample()
  src/sensors/
    SensorSuite.cpp            the sampling protocol, written once against the interfaces
    Pmsa003iFrame.cpp          the 32-byte frame decoder, shared by every driver
    ReadingsJson.cpp           the wire format in docs/READINGS.md
    Shtc3Driver.cpp  Scd41Driver.cpp  ...          the real parts (not written yet)
    mock/
      EnvModel.{h,cpp}         one simulated room driving all four mocks coherently
      MockScd41.h  MockPmsa003i.h  MockBme688.h  MockShtc3.h
  test/                        host tests: mocks, JSON encoding, loop timing (native env, like the kit)
server/
  server.py                    config, pages, DisplayServer(...).run()
  sources/mock.py              MockReadingsSource — the same room model in Python, for page work
  pages/breathe.py  pages/comfort.py  pages/day.py
  static/
  config.example.yaml
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

Building without `-DUSE_MOCK_SENSORS` is a `#error` naming the four drivers to
write, not a link failure.

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

When the hardware arrives, each mock is corrected against a log of the real
part. The tests then pin the corrected behaviour.

## 7. Order of work, if you agree

1. Kit: `postJson`, `refresh_cycle()`, interval schedule, `ReadingsStore` + `IngestSource`, `POST /readings`. Tests for each. Weather-cal stays green.
   *Status 2026-09-04: the interval schedule is in (`every` / `pages` under `display_schedule`). `refresh_cycle()` was not needed: the awake loop composes the kit's WiFi, download, draw and back-off helpers directly. `postJson` and the kit's `POST /<name>` ingest routes (`DisplayServer(ingest=...)`) are in. `ReadingsStore` and `IngestSource` are open; the server keeps only the newest posted document, for the Diagnostics page.*
2. Env-monitor firmware scaffold: `platformio.ini`, `ISensor`, `EnvModel`, the four mocks, host tests. Builds for `esp32dev` with the mocks selected by a build flag.
3. Env-monitor server: `MockReadingsSource`, one `now.png` page, `config.example.yaml`, `server.py`. Renders end to end with the mock.
4. The awake loop in `main.cpp` against the mocks, posting to the local server. First full loop with no hardware.
   *Status 2026-09-04: done. Fetch and draw on the server's cadence, one readings document a minute posted to `/readings` with the board's `client` status beside it.*
5. Real drivers when the parts arrive; correct the mocks.

## 8. Decisions needed from you

1. **HTTP POST** for readings, with MQTT republish later — or MQTT from the start?
2. **Fan always on** (datasheet's active mode, better accuracy) or duty-cycled via the SET wire (less power and dust)? Default: always on; wire SET anyway so it can change in software.
3. **Which SCD41 breakout** was ordered? HARDWARE.md assumes Adafruit 5190.
4. Firmware layout: `firmware/` subdirectory, or `src/` at the repo root like weather-cal? Default: root, to match.
