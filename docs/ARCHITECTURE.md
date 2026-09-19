# Architecture — where CANARY departs from the kit, and how

How this device differs from the weather calendar that [epd](https://github.com/chrisjtwomey/epd)
came out of, and what it builds on the kit. [HARDWARE.md](HARDWARE.md) has the numbers; the
[Decision Log](#decision-log) has the history.

## 1. What the kit assumes

`epd` was extracted from a weather calendar, and its client model is that
device's: **wake, fetch a PNG, draw it, deep-sleep until the server says.**
The client is dumb and battery-powered. All data lives server-side. The
server decides *when* (`Canary-Next-Display-Refresh-Seconds`) and *what*
(`Canary-Next-URL`) from a daily list of wall-clock times.

## 2. What is different here

| | Weather calendar | Env monitor |
|---|---|---|
| Power | LiPo, years | **USB mains** (HARDWARE §7) |
| Data origin | server fetches from APIs | **the device holds the sensors**, in a dock the panel stands in |
| Cadence | 7 wakes a day | readings every few seconds, display every few minutes |
| Client between refreshes | deep sleep | **awake**: sensors need it (SCD41 periodic mode with ASC, BSEC calibration state, PM fan warm-up) |
| Panel | Inkplate 10, 4 greys used | Inkplate 5 Gen2, **8 greys** |

Three of those change the design. The panel is one config line.

## 3. Four differences in the design

### 3.1 The firmware runs awake loops, not `run_app()`

`run_app()` is epd's deep-sleep state machine. Keeping an ESP32 awake is not
a tweak to it; it is a different program, and each board has its own.

The dock, `src/dock/main.cpp`, is the one the sensors need:

```
setup:  80 MHz; wifi; ntp; I2C; BSEC; sensors.begin()
loop:   every 5 s     sensors.sample()     (SCD41 periodic, BME688 via BSEC, PMSA003I frames, SHTC3)
        every 60 s    POST /readings       one JSON document, with the dock's own status beside it;
                                           a refused document waits in PSRAM for the next one the server takes
        continuous    the PM fan and the status LED
BSEC:   a FreeRTOS task of its own; its state goes to NVS when accuracy first reaches 3 and every six hours after
LED:    a FreeRTOS task of its own, so the starting pattern runs while setup() blocks
```

The dock runs at 80 MHz rather than 240. Wi-Fi needs 80, and below it the
APB clock follows the processor, which would move the LED's PWM frequency
and the serial baud rate. So 80 is both the floor and the choice.

The PM module's fan runs for the 35 seconds before each post and stops after
it, which is 58% of the time. It is the dock's largest load, about 200 mA of
the sensors' 215, and the window covers the module's 30 second warm-up and
the sample that follows. `SensorSuite` counts no missed frame while the fan
is off, so stopping it does not make the module look dead.

The head, `src/main.cpp`, stays awake only because it is mains powered and
has no reason to sleep:

```
setup:  board.begin(); wifi; ntp
loop:   when the refresh header ends      GET the named page → draw; a failed fetch keeps the old image and backs off
        every 60 s                         POST /readings     the head's own status and nothing else
```

Both loops compose epd's WiFi, time, download, `postJson` and back-off
helpers and the logger; the head adds the image helpers and `IBoard`, the
dock needs no board at all. The kit stays a library, not a framework: it
does not need to know what a sensor is.

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

### 3.4 The device is a head and a dock

The panel and the sensors are two boards, in two halves of one enclosure:

- **Head**: the Inkplate 5 Gen2 and nothing else. Its I²C bus carries only its own expander, RTC and panel PMIC,
  and its regulator carries only itself.
- **Dock**: an ESP32-S3 (TinyS3), the four sensors on a regulator of their own, and the USB-C socket that powers
  both halves. A magnetic pogo connector carries 5 V and ground up to the head, which sits in the dock's cradle.

Three things forced it, all in [HARDWARE.md §7–§8](HARDWARE.md#7-power):

- **The bus.** With the chain on the Inkplate's bus, a jammed sensor also stopped panel refreshes and the panel
  temperature read, because the expander, the RTC and the PMIC share that bus.
- **The rail.** The Inkplate's regulator is 500 mA and also carries its ESP32 and panel PMIC. The sensors peak at
  ~470 mA on their own.
- **Heat and quiet.** The SCD41 wants a supply free of Wi-Fi bursts, and the dock's own regulator would reach
  thermal shutdown carrying the chain.

Nothing else leaves the head: its only connections are the two wires soldered to its power pads, which meet the
dock at the pogo connector.

### 3.5 One LED says whether the dock is well

The dock drives a yellow LED on IO6, behind a clear tile in the shell's front face. It shows one of three states:

| What the LED does | What it means |
|---|---|
| Pulsing at 120 a minute | Starting: `setup()` is connecting, or starting the sensors. |
| Pulsing at 60 a minute | Working: it is reading, and the server is taking its posts. |
| Three flashes, then five seconds steady | No network, a post the server would not take, or a sensor has stopped. |

The slow pulse is the heartbeat: a dock that has died goes dark, which a steady working state would hide. A pulse
is sixteen equal steps of light, spaced in time along a sine.

`StatusLed` turns the time into an LEDC duty and holds no hardware, so the pattern is tested on the host.
Brightness is perceived brightness, mapped through gamma 2.2 onto a 14-bit channel at 1 kHz. A task of its own
drives the pin, because `setup()` blocks for as long as the network takes and the starting pulse runs through it.

### 3.6 The headers carry canary's name, not the library's

Every header on the wire starts with `Canary-`, because the server's responses are canary's interface and a reader
of the traffic should not have to know which library built it. The kit builds the names from a prefix each product
sets: the server takes `header_prefix="Canary"`, the firmware takes `-DEPD_HEADER_PREFIX='"Canary"'`, and a
mismatch is silent, so both come from this repository.

| Direction | Header | Carries |
|---|---|---|
| Board to server | `Canary-Device`, `Canary-Device-Version` | which board, and what it runs |
| Server to board | `Canary-Server-Version`, `Canary-Server-Epoch-Seconds` | on every response |
| Server to head | `Canary-Next-Display-Refresh-Seconds`, `Canary-Next-URL` | when to fetch, and what |
| Server to board | `Canary-Server-Firmware-Version`, `Canary-Server-Firmware-URL` | only when an update applies |

`GET /about` answers with the same version and clock, plus the firmware on offer and the library version. A board
asks at boot, after a post the server would not take, and once an hour.

The server's version is canary's own, from `git describe` when the image is built. It is not the `epd-server`
package's version: that package is a library this server is built with, and the two move independently.

### 3.7 When the two ends cannot work together

A board and the server work together when their major versions match, or, while the major is 0, their major and
minor. Both ends apply the rule, the server through `epd_server.compat` and the boards through `version_compat.h`,
so they reach the same answer about each other. A version that cannot be read, such as `dev`, is never judged:
refusing it would silently stop every development build.

The server's own version is the one the boards follow. It offers every released board the firmware for its
version, newer or older than what the board runs, so a mismatch clears itself once the board takes the offer.
Development builds are left alone.

- **The dock** gets 409 from `/readings` and holds the document in PSRAM rather than dropping it, since the reading
  is sound and only the pairing is wrong. The refused post puts the LED into its trouble pattern.
- **The head** still gets its pages, since the server never refuses a fetch. It draws a notice in place of the page
  and then takes any update on offer exactly as it would after a page. The order is fixed in
  `include/head/AfterFetch.h` and tested: the update is what clears the notice, and the dock's wall covers the
  head's USB-C socket.

The head draws a second notice when three fetches in a row go unanswered, about 26 minutes with the back-off, so a
blip never replaces the page. It says when the last page arrived. Both notices come from the firmware, not the
server, so they work when the server is what is wrong, and each is drawn once rather than on every retry, since
every draw is a full refresh of the panel.

They are pages. `server/pages/notice.py` sets each one like the others, a spaced-capitals label, an italic verdict
and a line of detail, and `scripts/notices.py` renders them through the same pipeline, browser and quantiser as
every page the server serves. The head holds the two PNGs in its firmware and draws them with the call that draws a
fetched page, so a notice is pixel for pixel what the server would have rendered. They are rendered again only when
their wording or design changes, so the firmware build needs no browser.

The layout leaves its bottom free for the two facts the head only knows at run time: when the last page arrived, or
the server's version, and then the board's own name, version and address. The head writes those in the pages' face
at the size of their detail text, from a one-bit font `scripts/gfxfont.py` makes out of the server's font file.

## 4. What stays as the kit has it

- The wire contract: `GET /<page>.png` with the refresh and next-URL headers. The awake client honours the header by waiting instead of sleeping.
- `DisplayServer`, `Page`, `regenerate()`, `DataSource`, the config loader, the MQTT log relay.
- `IBoard` and `EpdBoardInkplate`. Inkplate 5 Gen2 is `-DARDUINO_INKPLATE5V2`; GPIO39 RTC wake matches the schematic, though this device does not sleep.
- Rendering: `GreyscaleQuantiser` at eight levels for the panel's eight greys, one argument.

## 5. Shape of the repo

```
platformio.ini                 envs: esp32 (the head), dock (the TinyS3), dock-mock (-DUSE_MOCK_SENSORS), esp32-validate, native, sim
partitions.csv
src/main.cpp                   the head: fetch, draw, post its own state
src/dock/main.cpp              the dock: the awake loop from §3.1
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
include/dock/StatusLed.h       what the status LED shows, as a duty cycle (§3.5)
include/head/  src/notice.cpp  what the head does after a fetch, and the notices it draws (§3.7)
include/head/notices/          the notices, rendered by scripts/notices.py from server/pages/notice.py
include/head/fonts/            the pages' face as a one-bit font, from scripts/gfxfont.py, for the notices' live lines
src/sim/main.cpp               the sensor loop as a host binary
src/validate/main.cpp          the bench routine
lib/bme68x/                    Bosch's BME68x API
scripts/                       bsec.py, gfxfont.py, notices.py, version.py
test/                          host tests, native env
server/
  server.py                    config, sources, pages, DisplayServer(...).run()
  about.py  version.py         GET /about, and what this server calls itself
  sources/                     the mock room, readings ingest, calibration store, device status, sea-level pressure
  pages/                       Breathe, Comfort, Dust, Air, Day, Diagnostics, and the trace and delta pages
  metrics.py                   derived values and wording
  static/                      CSS, fonts, charts.js
  config.example.yaml
hardware/                      the desk enclosure
docs/
```

## 5.1 The sensor seam

`src/dock/main.cpp` names a concrete sensor type in exactly one place, a
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
parts. The `dock` and `dock-mock` environments are that one flag apart.

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
Each mock implements its part's interface (`IShtc3`, `IScd41`, `IPmsa003i`,
`IBme688`) and reproduces what the datasheet says the real part does:

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
- **2026-09-03**: the first draft planned one `ISensor` (`begin()` / `poll(now)` / `read(out)` / `sleep()`) with one `Reading` struct for all four parts. It was never built. The sensors could not share an interface because they do not share the same sampling sequence. The code has one interface for each part, and `SensorSuite` runs each part's sequence in turn. It also gives the SCD41 the BME688's pressure, and it drives the PM module's fan.
- **2026-09-04**: epd's `display` block landed: `pools` of images and a `schedule` of type `times` or `interval`, round-robin over pools and within them, with random starts reshuffled every few hours. `postJson` and `DisplayServer(ingest=...)` landed. `refresh_cycle()` was not needed: the awake loop composes the kit's WiFi, download, draw and back-off helpers directly. The awake loop ran end to end against the mocks, drawing on the server's cadence and posting one readings document a minute with the board's `client` status. Until the store existed, the server kept only the newest document, for the Diagnostics page.
- **2026-09-04**: the build settled three of the four questions. Readings go by HTTP POST: one route in `DisplayServer`, testable with Flask's test client, and an MQTT republish can follow on the server when Home Assistant enters the picture, with no change to the firmware. The firmware sits at the repo root, like the weather calendar's. The PM fan runs all the time.
- **2026-09-09**: the four drivers landed behind `II2cBus`, with host tests. The SCD41 board is the Adafruit 5190 (inventory item 92). The mocks were not corrected against logs of the real parts; that needs a log of each part.
- **2026-09-12**: `ReadingsStore` and `IngestSource` are in epd from 0.5.0, and `source.kind: store` serves them to the pages. BSEC runs for the BME688's IAQ index.
- **2026-09-15**: the device became a head and a dock (§3.4). One bus and one 500 mA rail could not carry both the panel and the sensor chain; each half now has its own.
