# Contributing to Inkplate 5 Environment Monitor

This project is at the design stage. The plan, and the status of the work
that makes it possible, is in [docs/EXTRACTION-PLAN.md](docs/EXTRACTION-PLAN.md).

## What it will be

A thin consumer of [epd](https://github.com/chrisjtwomey/epd), in the same
shape as [inkplate10-weather-cal](https://github.com/chrisjtwomey/inkplate10-weather-cal):

```
platformio.ini            -DARDUINO_INKPLATE5V2; lib_deps symlink://../epd/firmware
src/main.cpp              which IBoard to use
src/defaults.example.cpp  copy to defaults.cpp: WiFi, server URL, MQTT logging
server/
  server.py               config keys, a DataSource, a page list, DisplayServer(...).run()
  sources/                where the readings come from
  pages/                  the views
  static/                 CSS, icons, fonts
  config.example.yaml
```

Everything generic — the client firmware, HTTP, scheduling, rendering — is
epd. If a change is not about this device's sensors or pages, it goes there,
with its tests.

## Running it

No sensors and no board are needed to see the client work. Three ways, fastest
feedback first.

### 1. On your machine

`pio run -e sim` builds the client's sensor loop as a host binary: the same
`EnvModel`, the same mocks, the same `SensorSuite` the firmware runs —
everything but `Arduino.h`.

```sh
pio run -e sim
.pio/build/sim/program --help

.pio/build/sim/program                            # a day, five-minute samples, instantly
.pio/build/sim/program --start 17:00 --hours 4 --interval 600   # the evening: cooking spike, CO2 climb
.pio/build/sim/program --start 08:00 --hours 0.02 --interval 5  # the PM fan's 30 s warm-up
.pio/build/sim/program --speed 60                 # watch it unfold, a minute a second
.pio/build/sim/program --json --hours 0.01        # the JSON the device POSTs
```

The `sensors` column shows which parts reported: `T` temp/humidity, `C` CO₂,
`P` particulates, `G` gas. A dot means no reading — expected while the PM fan
warms up and between the SCD41's five-second conversions.

### 2. Host tests

```sh
pio test -e native            # room model, sensor mocks, SensorSuite protocol
```

### 3. On the Inkplate

Works today with the mocks: no sensors need to be wired.

```sh
pio run -e esp32 -t upload
pio device monitor -b 115200
```

It prints one readings document every five seconds. Swapping in real hardware
means writing four drivers against the `IShtc3` / `IScd41` / `IPmsa003i` /
`IBme688` interfaces and clearing `-DUSE_MOCK_SENSORS`; building without that
flag is an `#error` naming them.

## Setup

epd must be checked out beside this repo. Then, once the server exists:

```sh
python3 -m venv server/.venv && source server/.venv/bin/activate
pip install -r server/requirements-dev.txt
pip install -e ../epd/server        # develop against the local kit
```

## Making Changes

- Please fork the repository and create a new branch for your changes.
- Add a test for every behaviour you add or change.
- Comments describe the present, not the change. Git holds the history.
- Follow the policy in the [AI-Assisted Code](#ai-assisted-code) section when AI tools are used.

## AI-Assisted Code

If your change was written by an AI tool (such as GitHub Copilot, Claude, or similar), add a `Co-Authored-By` trailer to the commit message naming the tool.

Example commit message:

```
Add new feature X

Co-Authored-By: Claude <noreply@anthropic.com>
```

## Submitting Pull Requests

- Ensure your changes build and pass tests.
- Open a pull request with a clear description of your changes.
- Reference any related issues.
