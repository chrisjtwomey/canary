# CANARY

An indoor air-quality display: CO₂, particulates, VOC and temperature on a
5.2" e-paper panel, rendered server-side.

The dock checks the four sensors every minute and takes a reading on the
server's slots, every five minutes and every half hour overnight. It posts
the readings to the server, and the head shows the pages the server renders
from them in turn. A simulated room stands in for the sensors on the host
and on a board with nothing attached.

| | |
|---|---|
| CO₂ | Sensirion SCD41 |
| PM1.0 / PM2.5 / PM10 | Plantower PMSA003I (Adafruit breakout) |
| VOC, gas, pressure | Bosch BME688 (Soldered breakout) |
| Temperature, humidity | Sensirion SHTC3 (Soldered breakout) — the reference |
| Display / controller | Soldered Inkplate 5 Gen2 (ESP32-WROVER-E) |

All four sensors hang off one I²C bus over Qwiic/easyC, and the device runs
from USB-C; [hardware/bom.md](hardware/bom.md) has the power budget.

## Documentation

| | |
|---|---|
| [hardware/](hardware/README.md) | The two boards and the desk enclosure they sit in, and where the rest of the hardware docs are. |
| [hardware/bom.md](hardware/bom.md) | What to buy, what each part does, what else would do, and roughly what it costs. |
| [hardware/assembly.md](hardware/assembly.md) | How to build one, in order, with a picture at each step. |
| [hardware/enclosure.md](hardware/enclosure.md) | The printed parts: shape, fit, fasteners and the rules the Fusion model follows. |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | How this departs from the weather calendar's model, and how it builds on [epd](https://github.com/chrisjtwomey/epd). |
| [docs/READINGS.md](docs/READINGS.md) | The JSON the firmware posts. |

## Build and test

epd must be checked out beside this repo.

```sh
pio test -e native     # host tests: room model, mocks, drivers
pio run -e esp32       # the head: fetches and draws the pages
pio run -e dock        # the dock: the sensor drivers; -e dock-mock uses the simulated room
```

```sh
cd server
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pip install -e ../../epd/server     # the local kit, last: CONTRIBUTING.md, Setup, says why
pytest
```

Rendering needs Chrome. Then:

```sh
cp config.example.yaml config.yaml
python3 server.py --once                                   # every page -> server/*.png
python3 server.py --only breathe.png --at 2026-09-03T21:45  # one page, clock pinned
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the pages and the render loop.

`pio run -e dock -t upload` then `pio device monitor` shows the dock print
one readings document a minute; `-e dock-mock` does the same with the
simulated room in place of the sensors. `pio run -e esp32 -t upload` shows
the head fetch a page every five minutes. [CONTRIBUTING.md](CONTRIBUTING.md)
has the setup.

## The mocks

`EnvModel` is a simulated room: CO₂ rises with occupancy and decays with
ventilation, windows open twice a day, cooking spikes particulates and VOCs,
the heating follows a schedule. It exists in C++ and in Python, pinned to the
same pseudo-random sequence, so the firmware and the page rendering see the
same shapes.

Each mock reproduces its datasheet's timing and quirks rather than its
registers: the SCD41's 5 s cadence and untrustworthy first reading, the
PMSA003I's 30 s fan warm-up and occasional bad checksum, the BME688's
unstable first heater cycle, the SHTC3's 13 ms measurement and sleep.
