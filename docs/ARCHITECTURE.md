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
  src/sensors/
    ISensor.h                  begin() / poll(now) / read(out) / sleep(); one Reading struct
    Scd41.{h,cpp}  Pmsa003i.{h,cpp}  Bme688.{h,cpp}  Shtc3.{h,cpp}     wrap the vendor libraries
    mock/
      EnvModel.{h,cpp}         one simulated room driving all four mocks coherently
      MockScd41.h  MockPmsa003i.h  MockBme688.h  MockShtc3.h
  test/                        host tests: mocks, JSON encoding, loop timing (native env, like the kit)
server/
  server.py                    config, pages, DisplayServer(...).run()
  sources/mock.py              MockReadingsSource — the same room model in Python, for page work
  pages/now.py  pages/trend.py
  static/
  config.example.yaml
```

## 6. Mocks — what "as close as possible" means

The value is in the **timing and the quirks**, not in emulating registers.
Each mock implements `ISensor` and reproduces what the datasheet says the
real part does:

| Mock | Reproduces |
|---|---|
| `MockScd41` | 5 s measurement interval; `data_ready` false in between; first shot after power-up discarded; ±10 ppm repeatability noise; T reads +4 °C over the room until an offset is set; responds to `set_ambient_pressure` |
| `MockPmsa003i` | 30 s fan spin-up with unstable/zero frames; 2.3 s frame cadence; occasional checksum failure (1 in 200); stale identical frames between updates; SET-low = no frames |
| `MockBme688` | forced-mode timing (TPH + 100 ms heater); `heat_stab` false on the first cycle; gas resistance falls with VOC and with humidity; T reads +1.5 °C over the room; pressure tracks the model |
| `MockShtc3` | 12 ms measurement; sleep/wake; ±0.1 °C / ±0.1 % RH repeatability; the reference truth of the room |

`EnvModel` is the room: CO₂ rises with occupancy and decays with ventilation
(τ ≈ 60–90 min), PM has cooking/cleaning spikes, VOC has a baseline and
events, T/RH follow a diurnal curve with the heating on. The same model,
ported to Python, feeds `MockReadingsSource` so the pages are developed
against the same shapes the firmware will send.

When the hardware arrives, each mock is corrected against a log of the real
part. The tests then pin the corrected behaviour.

## 7. Order of work, if you agree

1. Kit: `postJson`, `refresh_cycle()`, interval schedule, `ReadingsStore` + `IngestSource`, `POST /readings`. Tests for each. Weather-cal stays green.
2. Env-monitor firmware scaffold: `platformio.ini`, `ISensor`, `EnvModel`, the four mocks, host tests. Builds for `esp32dev` with the mocks selected by a build flag.
3. Env-monitor server: `MockReadingsSource`, one `now.png` page, `config.example.yaml`, `server.py`. Renders end to end with the mock.
4. The awake loop in `main.cpp` against the mocks, posting to the local server. First full loop with no hardware.
5. Real drivers when the parts arrive; correct the mocks.

## 8. Decisions needed from you

1. **HTTP POST** for readings, with MQTT republish later — or MQTT from the start?
2. **Fan always on** (datasheet's active mode, better accuracy) or duty-cycled via the SET wire (less power and dust)? Default: always on; wire SET anyway so it can change in software.
3. **Which SCD41 breakout** was ordered? HARDWARE.md assumes Adafruit 5190.
4. Firmware layout: `firmware/` subdirectory, or `src/` at the repo root like weather-cal? Default: root, to match.
