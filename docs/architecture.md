# Architecture

How CANARY's firmware and server work. This page is the overview, and each topic has a doc of its own. The
hardware is in [hardware/README.md](../hardware/README.md).

## The parts

- **The dock** (TinyS3, `src/dock/main.cpp`) reads the four sensors at the server's slots, queues each reading in
  PSRAM, and posts the queue to the server. It stays online, and light-sleeps between passes of its loop.
- **The display** (Inkplate 5 Gen2, `src/main.cpp`) wakes for each page. It fetches the page, draws it, posts its
  own status, and deep-sleeps. E-paper keeps its image with no power.
- **The server** (`server/`) keeps the readings, draws the pages, holds the schedules and the dock's settings, and
  offers firmware to both boards.

| | Dock | Display |
|---|---|---|
| Board | TinyS3 (ESP32-S3) | Inkplate 5 Gen2 (ESP32-WROVER-E) |
| Between tasks | Light sleep, with Wi-Fi kept | Deep sleep |
| By default | A reading every 5 minutes, and every 30 minutes from 01:00 to 07:00 | A page every 5 minutes, and a sync every 30 minutes |
| Asks the server | `POST /sensor-readings`, `GET /board-settings`, `POST` and `GET /calibration`, `GET /about` | `GET /<page>.png`, `POST /sensor-readings` |
| Power | 5 V from the USB-C socket | 5 V from the dock, through the pogo connector |

## Why two boards

The panel and the sensors are on two boards, in two halves of one enclosure. The display is the Inkplate and
nothing else: its I²C bus carries only its own expander, RTC and panel PMIC, and its regulator carries only itself.
The dock has the four sensors, on a regulator of their own. Three facts forced this
([hardware/parts.md](../hardware/parts.md)):

- **The bus.** With the sensors on the Inkplate's bus, a jammed sensor also stopped the panel refreshes and the
  panel's temperature read, because the expander, the RTC and the PMIC share that bus.
- **The rail.** The Inkplate's regulator gives 500 mA, and it also carries the ESP32 and the panel PMIC. The sensors
  alone peak at about 470 mA.
- **Heat and noise.** The SCD41 needs a supply free of Wi-Fi bursts, and the TinyS3's own regulator would reach
  thermal shutdown if it carried the sensors.

The only connection between the two halves is the pogo connector, which carries 5 V and ground to the display.

## What comes from epd

CANARY uses [epd](https://github.com/chrisjtwomey/epd) for the generic parts, and adds its sensors and its pages.
The kit is a library, not a framework: it does not need to know what a sensor is.

- **Firmware:** epd's Wi-Fi, time, download, `postJson`, back-off and log helpers. The display also uses the image
  helpers and `IBoard` (`EpdBoardInkplate`, built with `-DARDUINO_INKPLATE5V2`). The dock needs no board.
- **Not `run_app()`:** that is epd's deep-sleep program for a board that only draws pages. Each board here does
  more, so each has its own program.
- **Server:** `DisplayServer`, `Page`, `regenerate()`, `DataSource`, the config loader, the readings store and the
  MQTT log relay.
- **Rendering:** `GreyscaleQuantiser` at eight levels, for the panel's eight greys.
- **The wire contract:** `GET /<page>.png`, with the headers that say when to fetch next and what
  ([versions.md](versions.md)).

## Topics

| Doc | What it covers |
|---|---|
| [dock.md](dock.md) | The dock's loop, its clock, the readings queue, and the sensor code |
| [display.md](display.md) | The display's wakes, its notices and its splash screen |
| [schedules.md](schedules.md) | When the page changes, when the dock takes a reading, and when the display syncs |
| [led.md](led.md) | The dock's status LED |
| [versions.md](versions.md) | The headers, `/about`, which versions work together, and firmware updates |
| [dock-settings.md](dock-settings.md) | The dock's settings, which the server holds |
| [readings.md](readings.md) | The JSON that each board posts |
| [simulator.md](simulator.md) | The simulated room and the mock sensors |

## The repo

```
platformio.ini                 envs: esp32 (the display), dock (the TinyS3), dock-mock (-DUSE_MOCK_SENSORS), dock-validate, native, sim;
                               a -dev twin of each board env builds against an epd checkout
partitions.csv
src/main.cpp                   the display: fetch, draw, post its own state
src/dock/main.cpp              the dock's loop (dock.md)
src/defaults.example.cpp       copy to defaults.cpp: Wi-Fi, server URL, MQTT logging
include/sensors/  src/sensors/
  Readings.h  ReadingsJson.cpp                  what the sensors return, and the wire format in readings.md
  IShtc3.h  IScd41.h  IPmsa003i.h  IBme688.h    one interface per part, shaped by its datasheet
  IClock.h  II2cBus.h                           the clock and bus seams
  SensorSuite  SensorHealth                     the four sensors as one begin() and one sample(), and how they fare
  Shtc3Driver  Scd41Driver  Pmsa003iDriver  Bme688Driver  SensirionI2c  Pmsa003iFrame
  IBsec.h  BsecRunner  BsecLibrary              BSEC, in a task of its own
  SensorValidation                              the bench routine's checks
  mock/                                         EnvModel, LaggedValue and the four mocks
include/net/  src/net/         Backlog, BoardSettings, Calibration, ClientStatus, ResetReason, ServerClock, Stamp, Url
include/dock/                  StatusLed (led.md), FanWindow and PostTimer: when the fan runs and the next reading falls
include/display/               when the display wakes, what it does after a fetch, and the notices it draws (display.md)
src/notice.cpp                 the notices, with the facts only the display knows at run time
src/splash.cpp                 the splash screen, and the update's progress bar under it
include/display/notices/       the notices, rendered by scripts/notices.py from server/pages/notice.py
include/display/splash.png     the splash screen, rendered by scripts/notices.py from server/pages/splash.py
include/display/fonts/         the pages' face as one-bit fonts, from scripts/gfxfont.py, for the lines the display writes
src/sim/main.cpp               the sensor loop as a host binary
src/validate/main.cpp          the bench routine
lib/bme68x/                    Bosch's BME68x API
scripts/                       bsec.py, dock_core.py, gfxfont.py, notices.py, version.py
test/                          host tests, native env
server/
  server.py                    config, sources, pages, DisplayServer(...).run()
  about.py  version.py         GET /about, and what this server calls itself
  web.py  html_doc.py          /web/: the pages in a browser, the explorer, and GET /history
  config_page.py               /web/config: config.yaml as a form in tabs and as text, checked, saved, and restarted on;
                               whether each board runs the saved settings
  config_form.py               the form's fields, and how a filled-in form edits config.yaml
  transfer.py                  a store out to a file and back in, and what it holds, for the Storage tab
  board_logs.py                what each board logs over MQTT, for the Logs view
  schedule.py                  the dock's reading slots (schedules.md)
  off_hours.py                 the splash screen while the page schedule is off (schedules.md)
  dock_settings.py             the dock block and GET /board-settings (dock-settings.md)
  display_settings.py          whether the display runs the saved display and image blocks (schedules.md)
  sources/                     the mock room, readings ingest, calibration store, device status, the corrections
                               the pages see: sea-level pressure, and no IAQ below accuracy 3
  pages/                       Breathe, Comfort, Dust, Air, Day, the Diagnostics pages, the trace and delta pages, and
                               the splash screen with its logo
  metrics.py                   derived values and wording; the comfort boxes and their words
  static/                      CSS, fonts, charts.js; web.css, browse.js, explore.js, config.js and sheet.js for /web/
  config.example.yaml
hardware/                      the boards, the desk enclosure and how to build it (hardware/README.md)
docs/                          these docs, and the developer guides that CONTRIBUTING points to
```
